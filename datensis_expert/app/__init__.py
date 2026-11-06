import os
import re
import secrets
import sqlite3
from datetime import timedelta
from functools import wraps
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, abort, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

load_dotenv()
BASE = Path(__file__).resolve().parent.parent
DB = BASE / 'instance' / 'expert.sqlite3'
CATEGORIES = (
    ('documents', 'Documents', 'Nouveaux documents et justificatifs'),
    ('messages', 'Messages', 'Réponses du cabinet'),
    ('echeances', 'Échéances', 'Rappels des obligations'),
    ('demandes', 'Demandes', 'Suivi des demandes'),
    ('rendez_vous', 'Rendez-vous', 'Rendez-vous et modifications'),
)


def database():
    if 'db' not in g:
        g.db = sqlite3.connect(DB)
        g.db.row_factory = sqlite3.Row
        g.db.execute('PRAGMA foreign_keys=ON')
    return g.db


def csrf_token():
    if 'csrf' not in session:
        session['csrf'] = secrets.token_urlsafe(32)
    return session['csrf']


def require_csrf():
    if not secrets.compare_digest(request.form.get('csrf_token', ''), session.get('csrf', '')):
        abort(400, 'Jeton de formulaire invalide')


def role_required(role):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if session.get('role') != role:
                return redirect(url_for('cabinet_login' if role == 'cabinet' else 'portal'))
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def password_valid(value):
    return 12 <= len(value) <= 256 and bool(re.search(r'[A-Z]', value)) and bool(re.search(r'\d', value)) and bool(re.search(r'[^\w\s]', value))


def ensure_notification_prefs(db, uid):
    db.execute('INSERT OR IGNORE INTO notification_preferences (user_id) VALUES (?)', (uid,))
    db.commit()
    return db.execute('SELECT * FROM notification_preferences WHERE user_id=?', (uid,)).fetchone()


def create_app():
    app = Flask(__name__)
    secret = os.environ.get('SECRET_KEY', '')
    if len(secret) < 32:
        raise RuntimeError('SECRET_KEY doit contenir au moins 32 caracteres dans .env')
    app.secret_key = secret
    app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
                      SESSION_COOKIE_SECURE=os.environ.get('DATENSIS_ENV') == 'production',
                      PERMANENT_SESSION_LIFETIME=timedelta(hours=2), MAX_CONTENT_LENGTH=5 * 1024 * 1024)
    DB.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB) as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS documents (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, title TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'Reçu', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, author_role TEXT NOT NULL, body TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY, title TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'À faire', priority TEXT NOT NULL DEFAULT 'Normale', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS notification_preferences (
          user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
          documents INTEGER NOT NULL DEFAULT 1, messages INTEGER NOT NULL DEFAULT 1,
          echeances INTEGER NOT NULL DEFAULT 1, demandes INTEGER NOT NULL DEFAULT 1,
          rendez_vous INTEGER NOT NULL DEFAULT 1, email_enabled INTEGER NOT NULL DEFAULT 0,
          reminder_days INTEGER NOT NULL DEFAULT 3
        );
        ''')
        columns = {r[1] for r in db.execute('PRAGMA table_info(users)')}
        for column, definition in [('phone', "TEXT NOT NULL DEFAULT ''"), ('language', "TEXT NOT NULL DEFAULT 'fr'"), ('theme', "TEXT NOT NULL DEFAULT 'dark'")]:
            if column not in columns:
                db.execute(f'ALTER TABLE users ADD COLUMN {column} {definition}')
        db.commit()
    @app.teardown_appcontext
    def close_database(exc):
        db = g.pop('db', None)
        if db is not None:
            db.close()
    app.jinja_env.globals['csrf_token'] = csrf_token

    @app.after_request
    def headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.get('/')
    def home():
        return redirect(url_for('portal'))

    @app.route('/portail', methods=['GET', 'POST'])
    def portal():
        if session.get('role') == 'client':
            return redirect(url_for('client'))
        if request.method == 'POST':
            require_csrf()
            email = request.form.get('email', '').strip().lower()
            password = request.form.get('password', '')
            user = database().execute('SELECT * FROM users WHERE email=?', (email,)).fetchone()
            if user and check_password_hash(user['password_hash'], password):
                session.clear()
                session.permanent = True
                session.update(role='client', user_id=user['id'], name=user['name'])
                return redirect(url_for('client'))
            flash('Identifiants incorrects.', 'error')
        return render_template('portal.html')

    @app.route('/inscription', methods=['GET', 'POST'])
    def register():
        if request.method == 'POST':
            require_csrf()
            name = request.form.get('name', '').strip()
            email = request.form.get('email', '').strip().lower()
            password = request.form.get('password', '')
            if not 2 <= len(name) <= 100 or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email) or not password_valid(password):
                flash('Nom, e-mail ou mot de passe invalide (12 caractères, majuscule, chiffre et symbole requis).', 'error')
            else:
                try:
                    database().execute('INSERT INTO users (name,email,password_hash) VALUES (?,?,?)', (name, email, generate_password_hash(password)))
                    database().commit()
                    flash('Compte créé. Connectez-vous.', 'success')
                    return redirect(url_for('portal'))
                except sqlite3.IntegrityError:
                    flash('Cette adresse e-mail existe déjà.', 'error')
        return render_template('register.html')

    @app.route('/cabinet/connexion', methods=['GET', 'POST'])
    def cabinet_login():
        if request.method == 'POST':
            require_csrf()
            email = os.environ.get('CABINET_EMAIL', '').strip().lower()
            password = os.environ.get('CABINET_PASSWORD', '')
            if email and len(password) >= 12 and secrets.compare_digest(request.form.get('email', '').strip().lower(), email) and secrets.compare_digest(request.form.get('password', ''), password):
                session.clear()
                session.permanent = True
                session.update(role='cabinet', name='Cabinet DATENSIS')
                return redirect(url_for('cabinet'))
            flash('Accès cabinet refusé.', 'error')
        return render_template('cabinet_login.html')

    @app.get('/client')
    @role_required('client')
    def client():
        db = database()
        uid = session['user_id']
        user = db.execute('SELECT id,name,email,phone,language,theme FROM users WHERE id=?', (uid,)).fetchone()
        if user is None:
            session.clear()
            return redirect(url_for('portal'))
        prefs = ensure_notification_prefs(db, uid)
        docs = db.execute('SELECT * FROM documents WHERE user_id=? ORDER BY id DESC', (uid,)).fetchall()
        messages = db.execute('SELECT * FROM messages WHERE user_id=? ORDER BY id DESC LIMIT 30', (uid,)).fetchall()
        items = []
        if prefs['messages']:
            items += [dict(title='Message du cabinet', body=m['body'], created_at=m['created_at']) for m in messages if m['author_role'] == 'cabinet']
        if prefs['documents']:
            items += [dict(title='Document enregistré', body=d['title'], created_at=d['created_at']) for d in docs[:10]]
        items.sort(key=lambda x: x['created_at'], reverse=True)
        return render_template('client.html', user=user, notification_prefs=prefs,
                               notification_categories=CATEGORIES, notification_items=items[:20],
                               docs=docs, messages=list(reversed(messages)), echeances=[])

    @app.post('/client/notifications')
    @role_required('client')
    def client_notifications():
        require_csrf()
        uid = session['user_id']
        db = database()
        ensure_notification_prefs(db, uid)
        names = [x[0] for x in CATEGORIES] + ['email_enabled']
        vals = [int(request.form.get(name) == '1') for name in names]
        reminder = request.form.get('reminder_days', type=int)
        if reminder not in (1, 3, 7):
            abort(400, 'Délai de rappel invalide')
        db.execute('''UPDATE notification_preferences SET documents=?,messages=?,echeances=?,demandes=?,rendez_vous=?,email_enabled=?,reminder_days=? WHERE user_id=?''', (*vals, reminder, uid))
        db.commit()
        flash('Préférences de notification enregistrées.', 'success')
        return redirect(url_for('client') + '#notifications')

    @app.post('/client/parametres/profil')
    @role_required('client')
    def client_profile():
        require_csrf()
        name = request.form.get('name', '').strip()
        phone = request.form.get('phone', '').strip()
        if not 2 <= len(name) <= 100 or len(phone) > 30 or (phone and not re.fullmatch(r'[+0-9(). /-]{6,30}', phone)):
            flash('Nom ou numéro de téléphone invalide.', 'error')
        else:
            database().execute('UPDATE users SET name=?,phone=? WHERE id=?', (name, phone, session['user_id']))
            database().commit()
            session['name'] = name
            flash('Profil mis à jour.', 'success')
        return redirect(url_for('client') + '#parametres')

    @app.post('/client/parametres/mot-de-passe')
    @role_required('client')
    def client_password():
        require_csrf()
        uid = session['user_id']
        user = database().execute('SELECT password_hash FROM users WHERE id=?', (uid,)).fetchone()
        old = request.form.get('current_password', '')
        new = request.form.get('new_password', '')
        confirm = request.form.get('confirm_password', '')
        if not user or not check_password_hash(user['password_hash'], old):
            flash('Mot de passe actuel incorrect.', 'error')
        elif new != confirm or not password_valid(new) or secrets.compare_digest(old, new):
            flash('Nouveau mot de passe invalide, différent de la confirmation ou identique à l’ancien.', 'error')
        else:
            database().execute('UPDATE users SET password_hash=? WHERE id=?', (generate_password_hash(new), uid))
            database().commit()
            flash('Mot de passe modifié.', 'success')
        return redirect(url_for('client') + '#parametres')

    @app.post('/client/parametres/preferences')
    @role_required('client')
    def client_preferences():
        require_csrf()
        language = request.form.get('language', '')
        theme = request.form.get('theme', '')
        if language not in ('fr', 'en') or theme not in ('dark', 'light'):
            abort(400, 'Préférences invalides')
        database().execute('UPDATE users SET language=?,theme=? WHERE id=?', (language, theme, session['user_id']))
        database().commit()
        flash('Préférences enregistrées.', 'success')
        return redirect(url_for('client') + '#parametres')

    @app.post('/client/documents')
    @role_required('client')
    def client_document():
        require_csrf()
        title = request.form.get('title', '').strip()[:120]
        if title:
            database().execute('INSERT INTO documents (user_id,title) VALUES (?,?)', (session['user_id'], title))
            database().commit()
            flash("Référence du document enregistrée. Aucun fichier n'a été transféré.", 'success')
        return redirect(url_for('client') + '#documents')

    @app.post('/client/messages')
    @role_required('client')
    def client_message():
        require_csrf()
        body = request.form.get('body', '').strip()[:2000]
        if body:
            database().execute('INSERT INTO messages (user_id,author_role,body) VALUES (?,?,?)', (session['user_id'], 'client', body))
            database().commit()
        return redirect(url_for('client') + '#messages')

    @app.get('/cabinet')
    @role_required('cabinet')
    def cabinet():
        db = database()
        users = db.execute('SELECT id,name,email FROM users ORDER BY id DESC').fetchall()
        tasks = db.execute('SELECT * FROM tasks ORDER BY id DESC').fetchall()
        docs = db.execute('SELECT d.*,u.name AS client_name FROM documents d JOIN users u ON u.id=d.user_id ORDER BY d.id DESC LIMIT 20').fetchall()
        messages = db.execute('SELECT m.*,u.name AS client_name FROM messages m JOIN users u ON u.id=m.user_id ORDER BY m.id DESC LIMIT 30').fetchall()
        return render_template('cabinet.html', users=users, tasks=tasks, docs=docs, messages=messages)

    @app.post('/cabinet/taches')
    @role_required('cabinet')
    def cabinet_task():
        require_csrf()
        title = request.form.get('title', '').strip()[:150]
        priority = request.form.get('priority', 'Normale')
        if title and priority in {'Normale', 'Haute', 'Urgente'}:
            database().execute('INSERT INTO tasks (title,priority) VALUES (?,?)', (title, priority))
            database().commit()
        return redirect(url_for('cabinet') + '#taches')

    @app.post('/cabinet/taches/<int:task_id>/terminer')
    @role_required('cabinet')
    def complete_task(task_id):
        require_csrf()
        database().execute("UPDATE tasks SET status='Terminée' WHERE id=?", (task_id,))
        database().commit()
        return redirect(url_for('cabinet') + '#taches')

    @app.post('/cabinet/messages')
    @role_required('cabinet')
    def cabinet_message():
        require_csrf()
        uid = request.form.get('user_id', type=int)
        body = request.form.get('body', '').strip()[:2000]
        if uid and body and database().execute('SELECT 1 FROM users WHERE id=?', (uid,)).fetchone():
            database().execute('INSERT INTO messages (user_id,author_role,body) VALUES (?,?,?)', (uid, 'cabinet', body))
            database().commit()
        return redirect(url_for('cabinet') + '#messages')

    @app.post('/deconnexion')
    def logout():
        require_csrf()
        session.clear()
        return redirect(url_for('portal'))

    return app
