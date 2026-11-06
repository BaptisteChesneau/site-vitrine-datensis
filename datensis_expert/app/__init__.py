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
DB = BASE / "instance" / "expert.sqlite3"


def database():
    if "db" not in g:
        g.db = sqlite3.connect(DB)
        g.db.row_factory = sqlite3.Row
    return g.db


def csrf_token():
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return session["csrf"]


def require_csrf():
    if not secrets.compare_digest(request.form.get("csrf_token", ""), session.get("csrf", "")):
        abort(400, "Jeton de formulaire invalide")


def role_required(role):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if session.get("role") != role:
                return redirect(url_for("cabinet_login" if role == "cabinet" else "portal"))
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def create_app():
    app = Flask(__name__)
    secret = os.environ.get("SECRET_KEY", "")
    if len(secret) < 32:
        raise RuntimeError("SECRET_KEY doit contenir au moins 32 caracteres dans .env")
    app.secret_key = secret
    app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax", PERMANENT_SESSION_LIFETIME=timedelta(hours=2), MAX_CONTENT_LENGTH=5 * 1024 * 1024)
    DB.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB) as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS documents (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, title TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'Reçu', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, author_role TEXT NOT NULL, body TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY, title TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'À faire', priority TEXT NOT NULL DEFAULT 'Normale', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        """)
    app.teardown_appcontext(lambda exc: g.pop("db").close() if "db" in g else None)
    app.jinja_env.globals["csrf_token"] = csrf_token

    @app.after_request
    def headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/")
    def home():
        return redirect(url_for("portal"))

    @app.route("/portail", methods=["GET", "POST"])
    def portal():
        if session.get("role") == "client":
            return redirect(url_for("client"))
        if request.method == "POST":
            require_csrf()
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            user = database().execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
            if user and check_password_hash(user["password_hash"], password):
                session.clear()
                session.permanent = True
                session.update(role="client", user_id=user["id"], name=user["name"])
                return redirect(url_for("client"))
            flash("Identifiants incorrects.", "error")
        return render_template("portal.html")

    @app.route("/inscription", methods=["GET", "POST"])
    def register():
        if request.method == "POST":
            require_csrf()
            name = request.form.get("name", "").strip()
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            if not 2 <= len(name) <= 100 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email) or len(password) < 12:
                flash("Nom, adresse e-mail ou mot de passe invalide (12 caractères minimum).", "error")
            else:
                try:
                    database().execute("INSERT INTO users (name,email,password_hash) VALUES (?,?,?)", (name, email, generate_password_hash(password)))
                    database().commit()
                    flash("Compte créé. Connectez-vous.", "success")
                    return redirect(url_for("portal"))
                except sqlite3.IntegrityError:
                    flash("Cette adresse e-mail existe déjà.", "error")
        return render_template("register.html")

    @app.route("/cabinet/connexion", methods=["GET", "POST"])
    def cabinet_login():
        if request.method == "POST":
            require_csrf()
            email = os.environ.get("CABINET_EMAIL", "").strip().lower()
            password = os.environ.get("CABINET_PASSWORD", "")
            if email and len(password) >= 12 and secrets.compare_digest(request.form.get("email", "").strip().lower(), email) and secrets.compare_digest(request.form.get("password", ""), password):
                session.clear()
                session.permanent = True
                session.update(role="cabinet", name="Cabinet DATENSIS")
                return redirect(url_for("cabinet"))
            flash("Accès cabinet refusé.", "error")
        return render_template("cabinet_login.html")

    @app.get("/client")
    @role_required("client")
    def client():
        db = database()
        uid = session["user_id"]
        docs = db.execute("SELECT * FROM documents WHERE user_id=? ORDER BY id DESC", (uid,)).fetchall()
        messages = db.execute("SELECT * FROM messages WHERE user_id=? ORDER BY id DESC LIMIT 30", (uid,)).fetchall()
        return render_template("client.html", docs=docs, messages=list(reversed(messages)))

    @app.post("/client/documents")
    @role_required("client")
    def client_document():
        require_csrf()
        title = request.form.get("title", "").strip()[:120]
        if title:
            database().execute("INSERT INTO documents (user_id,title) VALUES (?,?)", (session["user_id"], title))
            database().commit()
            flash("Référence du document enregistrée. Aucun fichier n'a été transféré.", "success")
        return redirect(url_for("client") + "#documents")

    @app.post("/client/messages")
    @role_required("client")
    def client_message():
        require_csrf()
        body = request.form.get("body", "").strip()[:2000]
        if body:
            database().execute("INSERT INTO messages (user_id,author_role,body) VALUES (?,?,?)", (session["user_id"], "client", body))
            database().commit()
        return redirect(url_for("client") + "#messages")

    @app.get("/cabinet")
    @role_required("cabinet")
    def cabinet():
        db = database()
        users = db.execute("SELECT id,name,email FROM users ORDER BY id DESC").fetchall()
        tasks = db.execute("SELECT * FROM tasks ORDER BY id DESC").fetchall()
        docs = db.execute("SELECT d.*,u.name AS client_name FROM documents d JOIN users u ON u.id=d.user_id ORDER BY d.id DESC LIMIT 20").fetchall()
        messages = db.execute("SELECT m.*,u.name AS client_name FROM messages m JOIN users u ON u.id=m.user_id ORDER BY m.id DESC LIMIT 30").fetchall()
        return render_template("cabinet.html", users=users, tasks=tasks, docs=docs, messages=messages)

    @app.post("/cabinet/taches")
    @role_required("cabinet")
    def cabinet_task():
        require_csrf()
        title = request.form.get("title", "").strip()[:150]
        priority = request.form.get("priority", "Normale")
        if title and priority in {"Normale", "Haute", "Urgente"}:
            database().execute("INSERT INTO tasks (title,priority) VALUES (?,?)", (title, priority))
            database().commit()
        return redirect(url_for("cabinet") + "#taches")

    @app.post("/cabinet/taches/<int:task_id>/terminer")
    @role_required("cabinet")
    def complete_task(task_id):
        require_csrf()
        database().execute("UPDATE tasks SET status='Terminée' WHERE id=?", (task_id,))
        database().commit()
        return redirect(url_for("cabinet") + "#taches")

    @app.post("/cabinet/messages")
    @role_required("cabinet")
    def cabinet_message():
        require_csrf()
        uid = request.form.get("user_id", type=int)
        body = request.form.get("body", "").strip()[:2000]
        if uid and body and database().execute("SELECT 1 FROM users WHERE id=?", (uid,)).fetchone():
            database().execute("INSERT INTO messages (user_id,author_role,body) VALUES (?,?,?)", (uid, "cabinet", body))
            database().commit()
        return redirect(url_for("cabinet") + "#messages")

    @app.post("/deconnexion")
    def logout():
        require_csrf()
        session.clear()
        return redirect(url_for("portal"))

    return app
