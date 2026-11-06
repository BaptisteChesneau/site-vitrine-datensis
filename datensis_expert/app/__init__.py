
import hashlib
import logging
import os
import re
import secrets
import smtplib
import sqlite3

from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from functools import wraps
from pathlib import Path

from dotenv import load_dotenv
from flask import (
    Flask,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import (
    check_password_hash,
    generate_password_hash,
)


BASE = Path(__file__).resolve().parent.parent
load_dotenv(BASE / ".env")

DB = BASE / "instance" / "expert.sqlite3"

LOGGER = logging.getLogger(__name__)

CATEGORIES = (
    ("documents", "Documents", "Nouveaux documents et justificatifs"),
    ("messages", "Messages", "Réponses du cabinet"),
    ("echeances", "Échéances", "Rappels des obligations"),
    ("demandes", "Demandes", "Suivi des demandes"),
    ("rendez_vous", "Rendez-vous", "Rendez-vous et modifications"),
)

USER_COLUMNS = (
    ("phone", "TEXT NOT NULL DEFAULT ''"),
    ("language", "TEXT NOT NULL DEFAULT 'fr'"),
    ("theme", "TEXT NOT NULL DEFAULT 'dark'"),
    ("first_name", "TEXT NOT NULL DEFAULT ''"),
    ("last_name", "TEXT NOT NULL DEFAULT ''"),
    ("company_name", "TEXT NOT NULL DEFAULT ''"),
    ("siret", "TEXT NOT NULL DEFAULT ''"),
    ("legal_form", "TEXT NOT NULL DEFAULT ''"),
    ("activity", "TEXT NOT NULL DEFAULT ''"),
    ("address", "TEXT NOT NULL DEFAULT ''"),
    ("postal_code", "TEXT NOT NULL DEFAULT ''"),
    ("city", "TEXT NOT NULL DEFAULT ''"),
    ("country", "TEXT NOT NULL DEFAULT 'France'"),
)

REGISTRATION_FIELDS = {
    "first_name": 80,
    "last_name": 80,
    "phone": 30,
    "company_name": 200,
    "siret": 14,
    "legal_form": 50,
    "activity": 150,
    "address": 200,
    "postal_code": 10,
    "city": 100,
    "country": 80,
}

LEGAL_FORMS = {
    "EI",
    "Micro-entreprise",
    "EURL",
    "SARL",
    "SASU",
    "SAS",
    "SA",
    "SCI",
    "Association",
    "Autre",
}


def database():
    if "db" not in g:
        g.db = sqlite3.connect(DB)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
        g.db.execute("PRAGMA busy_timeout = 5000")

    return g.db


def csrf_token():
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)

    return session["csrf"]


def require_csrf():
    submitted = request.form.get("csrf_token", "")
    expected = session.get("csrf", "")

    if not expected or not secrets.compare_digest(submitted, expected):
        abort(400, "Jeton de formulaire invalide")


def role_required(role):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if session.get("role") != role:
                endpoint = "cabinet_login" if role == "cabinet" else "portal"
                return redirect(url_for(endpoint))

            return fn(*args, **kwargs)

        return wrapper

    return decorator


def password_valid(value):
    return (
        12 <= len(value) <= 256
        and bool(re.search(r"[A-Z]", value))
        and bool(re.search(r"\d", value))
        and bool(re.search(r"[^\w\s]", value))
    )


def email_valid(value):
    return (
        len(value) <= 254
        and bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value))
    )


def phone_valid(value):
    return bool(re.fullmatch(r"[+0-9(). /-]{6,30}", value))


def utc_now():
    return datetime.now(timezone.utc)


def token_hash(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def ensure_notification_prefs(db, uid):
    db.execute(
        """
        INSERT OR IGNORE INTO notification_preferences (user_id)
        VALUES (?)
        """,
        (uid,),
    )
    db.commit()

    return db.execute(
        """
        SELECT *
        FROM notification_preferences
        WHERE user_id = ?
        """,
        (uid,),
    ).fetchone()


def init_database():
    DB.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(DB) as db:
        db.execute("PRAGMA foreign_keys = ON")

        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Reçu',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                author_role TEXT NOT NULL,
                body TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'À faire',
                priority TEXT NOT NULL DEFAULT 'Normale',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS notification_preferences (
                user_id INTEGER PRIMARY KEY
                    REFERENCES users(id) ON DELETE CASCADE,
                documents INTEGER NOT NULL DEFAULT 1,
                messages INTEGER NOT NULL DEFAULT 1,
                echeances INTEGER NOT NULL DEFAULT 1,
                demandes INTEGER NOT NULL DEFAULT 1,
                rendez_vous INTEGER NOT NULL DEFAULT 1,
                email_enabled INTEGER NOT NULL DEFAULT 0,
                reminder_days INTEGER NOT NULL DEFAULT 3
            );

            CREATE TABLE IF NOT EXISTS password_reset_tokens (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL
                    REFERENCES users(id) ON DELETE CASCADE,
                token_hash TEXT NOT NULL UNIQUE,
                expires_at TEXT NOT NULL,
                used_at TEXT,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_reset_user
            ON password_reset_tokens(user_id);
            """
        )

        columns = {
            row[1]
            for row in db.execute("PRAGMA table_info(users)")
        }

        for column, definition in USER_COLUMNS:
            if column not in columns:
                db.execute(
                    f"ALTER TABLE users ADD COLUMN {column} {definition}"
                )

        db.commit()


def send_reset_email(recipient, reset_url):
    host = os.getenv("SMTP_HOST", "").strip()
    username = os.getenv("SMTP_USER", "").strip()
    password = os.getenv("SMTP_PASSWORD", "")
    sender = os.getenv("SMTP_FROM", "").strip()

    try:
        port = int(os.getenv("SMTP_PORT", "587"))
    except ValueError:
        LOGGER.error("Port SMTP invalide")
        return False

    if not host or not sender:
        LOGGER.warning("Configuration SMTP absente ou incomplète")
        return False

    if bool(username) != bool(password):
        LOGGER.warning("Identifiants SMTP incomplets")
        return False

    message = EmailMessage()
    message["Subject"] = "DATENSIS Expert - Réinitialisation du mot de passe"
    message["From"] = sender
    message["To"] = recipient

    message.set_content(
        "Bonjour,\n\n"
        "Une demande de réinitialisation de mot de passe "
        "a été effectuée pour votre compte DATENSIS Expert.\n\n"
        f"Utilisez ce lien :\n{reset_url}\n\n"
        "Ce lien est valable pendant 30 minutes "
        "et ne peut être utilisé qu'une seule fois.\n\n"
        "Si vous n'êtes pas à l'origine de cette demande, "
        "ignorez ce message.\n\n"
        "DATENSIS Expert"
    )

    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=15) as smtp:
                if username:
                    smtp.login(username, password)
                smtp.send_message(message)
        else:
            with smtplib.SMTP(host, port, timeout=15) as smtp:
                smtp.ehlo()
                smtp.starttls()
                smtp.ehlo()

                if username:
                    smtp.login(username, password)

                smtp.send_message(message)

        return True

    except (OSError, smtplib.SMTPException):
        LOGGER.exception("Échec de l'envoi du courriel de réinitialisation")
        return False


def create_app():
    app = Flask(__name__)

    secret = os.getenv("SECRET_KEY", "")

    if len(secret) < 32:
        raise RuntimeError(
            "SECRET_KEY doit contenir au moins 32 caractères dans .env"
        )

    app.secret_key = secret

    production = os.getenv("DATENSIS_ENV", "development") == "production"

    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=production,
        PERMANENT_SESSION_LIFETIME=timedelta(hours=2),
        MAX_CONTENT_LENGTH=5 * 1024 * 1024,
    )

    init_database()

    app.jinja_env.globals["csrf_token"] = csrf_token

    @app.teardown_appcontext
    def close_database(exc):
        db = g.pop("db", None)

        if db is not None:
            db.close()

    @app.after_request
    def security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Cache-Control"] = "no-store"

        return response

    # =====================================================
    # ACCUEIL
    # =====================================================

    @app.get("/")
    def home():
        return redirect(url_for("portal"))

    # =====================================================
    # CONNEXION CLIENT
    # =====================================================

    @app.route("/portail", methods=["GET", "POST"])
    def portal():
        if session.get("role") == "client":
            return redirect(url_for("client"))

        if request.method == "POST":
            require_csrf()

            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")

            user = database().execute(
                "SELECT * FROM users WHERE email = ?",
                (email,),
            ).fetchone()

            if user and check_password_hash(
                user["password_hash"],
                password,
            ):
                session.clear()
                session.permanent = True

                session.update(
                    role="client",
                    user_id=user["id"],
                    name=user["name"],
                )

                return redirect(url_for("client"))

            flash("Identifiants incorrects.", "error")

        return render_template("portal.html")

    # =====================================================
    # INSCRIPTION CLIENT
    # =====================================================

    @app.route("/inscription", methods=["GET", "POST"])
    def register():
        if session.get("role") == "client":
            return redirect(url_for("client"))

        if request.method == "POST":
            require_csrf()

            values = {
                field: request.form.get(field, "").strip()
                for field in REGISTRATION_FIELDS
            }

            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            confirm = request.form.get("confirm_password", "")
            terms = request.form.get("terms", "")

            errors = []

            for field, max_length in REGISTRATION_FIELDS.items():
                value = values[field]

                if field != "country" and not value:
                    errors.append(f"Le champ {field} est obligatoire.")

                if len(value) > max_length:
                    errors.append(f"Le champ {field} est trop long.")

            if not 2 <= len(values["first_name"]) <= 80:
                errors.append("Prénom invalide.")

            if not 2 <= len(values["last_name"]) <= 80:
                errors.append("Nom invalide.")

            if not email_valid(email):
                errors.append("Adresse e-mail invalide.")

            if not phone_valid(values["phone"]):
                errors.append("Numéro de téléphone invalide.")

            if not re.fullmatch(r"\d{14}", values["siret"]):
                errors.append("Le SIRET doit contenir 14 chiffres.")

            if values["legal_form"] not in LEGAL_FORMS:
                errors.append("Forme juridique invalide.")

            if not password_valid(password):
                errors.append(
                    "Le mot de passe doit contenir au moins "
                    "12 caractères, une majuscule, un chiffre "
                    "et un symbole."
                )

            if password != confirm:
                errors.append("Les mots de passe ne correspondent pas.")

            if terms != "accepted":
                errors.append(
                    "Vous devez accepter les conditions d'utilisation."
                )

            if errors:
                for error in dict.fromkeys(errors):
                    flash(error, "error")

                return render_template("register.html"), 400

            name = (
                f"{values['first_name']} {values['last_name']}"
            )

            db = database()

            try:
                cursor = db.execute(
                    """
                    INSERT INTO users (
                        name,
                        email,
                        password_hash,
                        first_name,
                        last_name,
                        phone,
                        company_name,
                        siret,
                        legal_form,
                        activity,
                        address,
                        postal_code,
                        city,
                        country
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        name,
                        email,
                        generate_password_hash(password),
                        values["first_name"],
                        values["last_name"],
                        values["phone"],
                        values["company_name"],
                        values["siret"],
                        values["legal_form"],
                        values["activity"],
                        values["address"],
                        values["postal_code"],
                        values["city"],
                        values["country"] or "France",
                    ),
                )

                user_id = cursor.lastrowid

                db.execute(
                    """
                    INSERT OR IGNORE INTO notification_preferences (user_id)
                    VALUES (?)
                    """,
                    (user_id,),
                )

                db.commit()

            except sqlite3.IntegrityError:
                db.rollback()
                flash("Cette adresse e-mail existe déjà.", "error")
                return render_template("register.html"), 409

            session.clear()
            session.permanent = True

            session.update(
                role="client",
                user_id=user_id,
                name=name,
            )

            flash(
                "Votre compte a été créé. Bienvenue dans votre espace.",
                "success",
            )

            return redirect(url_for("client"))

        return render_template("register.html")

    # =====================================================
    # MOT DE PASSE OUBLIÉ
    # =====================================================

    @app.route(
        "/mot-de-passe-oublie",
        methods=["GET", "POST"],
    )
    def forgot_password():
        if request.method == "POST":
            require_csrf()

            email = request.form.get("email", "").strip().lower()

            if not email_valid(email):
                flash("Adresse e-mail invalide.", "error")
                return render_template("forgot_password.html"), 400

            db = database()

            user = db.execute(
                "SELECT id FROM users WHERE email = ?",
                (email,),
            ).fetchone()

            if user:
                token = secrets.token_urlsafe(48)
                hashed = token_hash(token)

                created = utc_now()
                expires = created + timedelta(minutes=30)

                reset_url = url_for(
                    "reset_password",
                    token=token,
                    _external=True,
                )

                # Le lien n'est envoyé que si SMTP est configuré.
                if send_reset_email(email, reset_url):
                    db.execute(
                        """
                        UPDATE password_reset_tokens
                        SET used_at = ?
                        WHERE user_id = ? AND used_at IS NULL
                        """,
                        (created.isoformat(), user["id"]),
                    )

                    db.execute(
                        """
                        INSERT INTO password_reset_tokens (
                            user_id,
                            token_hash,
                            expires_at,
                            created_at
                        )
                        VALUES (?, ?, ?, ?)
                        """,
                        (
                            user["id"],
                            hashed,
                            expires.isoformat(),
                            created.isoformat(),
                        ),
                    )

                    db.commit()

            flash(
                "Si un compte correspond à cette adresse "
                "et que le service d'envoi est disponible, "
                "un lien de réinitialisation vous sera envoyé.",
                "success",
            )

            return redirect(url_for("portal"))

        return render_template("forgot_password.html")

    # =====================================================
    # RÉINITIALISATION DU MOT DE PASSE
    # =====================================================

    @app.route(
        "/reinitialiser-mot-de-passe/<token>",
        methods=["GET", "POST"],
    )
    def reset_password(token):
        if len(token) > 256:
            abort(404)

        hashed = token_hash(token)

        db = database()

        reset = db.execute(
            """
            SELECT *
            FROM password_reset_tokens
            WHERE token_hash = ?
              AND used_at IS NULL
              AND expires_at > ?
            """,
            (hashed, utc_now().isoformat()),
        ).fetchone()

        if reset is None:
            flash(
                "Ce lien est invalide ou a expiré.",
                "error",
            )
            return redirect(url_for("forgot_password"))

        if request.method == "POST":
            require_csrf()

            password = request.form.get("password", "")
            confirm = request.form.get("confirm_password", "")

            if password != confirm or not password_valid(password):
                flash(
                    "Mot de passe invalide ou confirmation incorrecte.",
                    "error",
                )
                return render_template("reset_password.html")

            now = utc_now().isoformat()

            try:
                db.execute("BEGIN IMMEDIATE")

                claimed = db.execute(
                    """
                    UPDATE password_reset_tokens
                    SET used_at = ?
                    WHERE id = ?
                      AND used_at IS NULL
                      AND expires_at > ?
                    """,
                    (now, reset["id"], now),
                )

                if claimed.rowcount != 1:
                    db.rollback()
                    flash(
                        "Ce lien n'est plus valide.",
                        "error",
                    )
                    return redirect(url_for("forgot_password"))

                db.execute(
                    """
                    UPDATE users
                    SET password_hash = ?
                    WHERE id = ?
                    """,
                    (
                        generate_password_hash(password),
                        reset["user_id"],
                    ),
                )

                db.execute(
                    """
                    UPDATE password_reset_tokens
                    SET used_at = ?
                    WHERE user_id = ? AND used_at IS NULL
                    """,
                    (now, reset["user_id"]),
                )

                db.commit()

            except sqlite3.Error:
                db.rollback()
                LOGGER.exception("Erreur de réinitialisation du mot de passe")
                abort(500)

            session.clear()

            flash(
                "Votre mot de passe a été modifié. "
                "Vous pouvez vous connecter.",
                "success",
            )

            return redirect(url_for("portal"))

        return render_template("reset_password.html")

    # =====================================================
    # CONNEXION CABINET
    # =====================================================

    @app.route(
        "/cabinet/connexion",
        methods=["GET", "POST"],
    )
    def cabinet_login():
        if request.method == "POST":
            require_csrf()

            email = os.getenv("CABINET_EMAIL", "").strip().lower()
            password = os.getenv("CABINET_PASSWORD", "")

            submitted_email = request.form.get("email", "").strip().lower()
            submitted_password = request.form.get("password", "")

            valid = (
                bool(email)
                and len(password) >= 12
                and secrets.compare_digest(submitted_email, email)
                and secrets.compare_digest(submitted_password, password)
            )

            if valid:
                session.clear()
                session.permanent = True

                session.update(
                    role="cabinet",
                    name="Cabinet DATENSIS",
                )

                return redirect(url_for("cabinet"))

            flash("Accès cabinet refusé.", "error")

        return render_template("cabinet_login.html")

    # =====================================================
    # ESPACE CLIENT
    # =====================================================

    @app.get("/client")
    @role_required("client")
    def client():
        db = database()
        uid = session["user_id"]

        user = db.execute(
            "SELECT * FROM users WHERE id = ?",
            (uid,),
        ).fetchone()

        if user is None:
            session.clear()
            return redirect(url_for("portal"))

        prefs = ensure_notification_prefs(db, uid)

        docs = db.execute(
            """
            SELECT *
            FROM documents
            WHERE user_id = ?
            ORDER BY id DESC
            """,
            (uid,),
        ).fetchall()

        messages = db.execute(
            """
            SELECT *
            FROM messages
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT 30
            """,
            (uid,),
        ).fetchall()

        items = []

        if prefs["messages"]:
            items.extend(
                {
                    "title": "Message du cabinet",
                    "body": msg["body"],
                    "created_at": msg["created_at"],
                }
                for msg in messages
                if msg["author_role"] == "cabinet"
            )

        if prefs["documents"]:
            items.extend(
                {
                    "title": "Document enregistré",
                    "body": doc["title"],
                    "created_at": doc["created_at"],
                }
                for doc in docs[:10]
            )

        items.sort(
            key=lambda item: item["created_at"],
            reverse=True,
        )

        return render_template(
            "client.html",
            user=user,
            notification_prefs=prefs,
            notification_categories=CATEGORIES,
            notification_items=items[:20],
            docs=docs,
            messages=list(reversed(messages)),
            echeances=[],
        )

    # =====================================================
    # NOTIFICATIONS CLIENT
    # =====================================================

    @app.post("/client/notifications")
    @role_required("client")
    def client_notifications():
        require_csrf()

        uid = session["user_id"]
        db = database()

        ensure_notification_prefs(db, uid)

        names = [category[0] for category in CATEGORIES]
        names.append("email_enabled")

        values = [
            int(request.form.get(name) == "1")
            for name in names
        ]

        reminder = request.form.get("reminder_days", type=int)

        if reminder not in (1, 3, 7):
            abort(400, "Délai de rappel invalide")

        db.execute(
            """
            UPDATE notification_preferences
            SET documents = ?,
                messages = ?,
                echeances = ?,
                demandes = ?,
                rendez_vous = ?,
                email_enabled = ?,
                reminder_days = ?
            WHERE user_id = ?
            """,
            (*values, reminder, uid),
        )

        db.commit()

        flash(
            "Préférences de notification enregistrées.",
            "success",
        )

        return redirect(url_for("client") + "#notifications")

    # =====================================================
    # PROFIL CLIENT
    # =====================================================

    @app.post("/client/parametres/profil")
    @role_required("client")
    def client_profile():
        require_csrf()

        name = request.form.get("name", "").strip()
        phone = request.form.get("phone", "").strip()

        valid = (
            2 <= len(name) <= 100
            and len(phone) <= 30
            and (not phone or phone_valid(phone))
        )

        if not valid:
            flash(
                "Nom ou numéro de téléphone invalide.",
                "error",
            )
        else:
            db = database()

            db.execute(
                """
                UPDATE users
                SET name = ?, phone = ?
                WHERE id = ?
                """,
                (name, phone, session["user_id"]),
            )

            db.commit()

            session["name"] = name

            flash("Profil mis à jour.", "success")

        return redirect(url_for("client") + "#parametres")

    # =====================================================
    # MODIFIER MOT DE PASSE CLIENT
    # =====================================================

    @app.post("/client/parametres/mot-de-passe")
    @role_required("client")
    def client_password():
        require_csrf()

        uid = session["user_id"]
        db = database()

        user = db.execute(
            """
            SELECT password_hash
            FROM users
            WHERE id = ?
            """,
            (uid,),
        ).fetchone()

        old = request.form.get("current_password", "")
        new = request.form.get("new_password", "")
        confirm = request.form.get("confirm_password", "")

        if not user or not check_password_hash(
            user["password_hash"],
            old,
        ):
            flash("Mot de passe actuel incorrect.", "error")

        elif (
            new != confirm
            or not password_valid(new)
            or secrets.compare_digest(old, new)
        ):
            flash(
                "Nouveau mot de passe invalide, différent "
                "de la confirmation ou identique à l'ancien.",
                "error",
            )

        else:
            db.execute(
                """
                UPDATE users
                SET password_hash = ?
                WHERE id = ?
                """,
                (
                    generate_password_hash(new),
                    uid,
                ),
            )

            db.commit()

            flash("Mot de passe modifié.", "success")

        return redirect(url_for("client") + "#parametres")

    # =====================================================
    # PRÉFÉRENCES CLIENT
    # =====================================================

    @app.post("/client/parametres/preferences")
    @role_required("client")
    def client_preferences():
        require_csrf()

        language = request.form.get("language", "")
        theme = request.form.get("theme", "")

        if language not in ("fr", "en"):
            abort(400, "Langue invalide")

        if theme not in ("dark", "light"):
            abort(400, "Thème invalide")

        db = database()

        db.execute(
            """
            UPDATE users
            SET language = ?, theme = ?
            WHERE id = ?
            """,
            (
                language,
                theme,
                session["user_id"],
            ),
        )

        db.commit()

        flash("Préférences enregistrées.", "success")

        return redirect(url_for("client") + "#parametres")

    # =====================================================
    # DOCUMENTS CLIENT
    # =====================================================

    @app.post("/client/documents")
    @role_required("client")
    def client_document():
        require_csrf()

        title = request.form.get("title", "").strip()[:120]

        if title:
            db = database()

            db.execute(
                """
                INSERT INTO documents (user_id, title)
                VALUES (?, ?)
                """,
                (session["user_id"], title),
            )

            db.commit()

            flash(
                "Référence documentaire enregistrée. "
                "Aucun fichier n'a été transféré.",
                "success",
            )

        return redirect(url_for("client") + "#documents")

    # =====================================================
    # MESSAGES CLIENT
    # =====================================================

    @app.post("/client/messages")
    @role_required("client")
    def client_message():
        require_csrf()

        body = request.form.get("body", "").strip()[:2000]

        if body:
            db = database()

            db.execute(
                """
                INSERT INTO messages (
                    user_id,
                    author_role,
                    body
                )
                VALUES (?, ?, ?)
                """,
                (
                    session["user_id"],
                    "client",
                    body,
                ),
            )

            db.commit()

        return redirect(url_for("client") + "#messages")

    # =====================================================
    # ESPACE CABINET
    # =====================================================

    @app.get("/cabinet")
    @role_required("cabinet")
    def cabinet():
        db = database()

        users = db.execute(
            """
            SELECT id, name, email
            FROM users
            ORDER BY id DESC
            """
        ).fetchall()

        tasks = db.execute(
            """
            SELECT *
            FROM tasks
            ORDER BY id DESC
            """
        ).fetchall()

        docs = db.execute(
            """
            SELECT d.*, u.name AS client_name
            FROM documents d
            JOIN users u ON u.id = d.user_id
            ORDER BY d.id DESC
            LIMIT 20
            """
        ).fetchall()

        messages = db.execute(
            """
            SELECT m.*, u.name AS client_name
            FROM messages m
            JOIN users u ON u.id = m.user_id
            ORDER BY m.id DESC
            LIMIT 30
            """
        ).fetchall()

        return render_template(
            "cabinet.html",
            users=users,
            tasks=tasks,
            docs=docs,
            messages=messages,
        )

    # =====================================================
    # TÂCHES CABINET
    # =====================================================

    @app.post("/cabinet/taches")
    @role_required("cabinet")
    def cabinet_task():
        require_csrf()

        title = request.form.get("title", "").strip()[:150]
        priority = request.form.get("priority", "Normale")

        if title and priority in {"Normale", "Haute", "Urgente"}:
            db = database()

            db.execute(
                """
                INSERT INTO tasks (title, priority)
                VALUES (?, ?)
                """,
                (title, priority),
            )

            db.commit()

        return redirect(url_for("cabinet") + "#taches")

    @app.post("/cabinet/taches/<int:task_id>/terminer")
    @role_required("cabinet")
    def complete_task(task_id):
        require_csrf()

        db = database()

        db.execute(
            """
            UPDATE tasks
            SET status = 'Terminée'
            WHERE id = ?
            """,
            (task_id,),
        )

        db.commit()

        return redirect(url_for("cabinet") + "#taches")

    # =====================================================
    # MESSAGES CABINET
    # =====================================================

    @app.post("/cabinet/messages")
    @role_required("cabinet")
    def cabinet_message():
        require_csrf()

        uid = request.form.get("user_id", type=int)
        body = request.form.get("body", "").strip()[:2000]

        db = database()

        user_exists = (
            uid is not None
            and db.execute(
                "SELECT 1 FROM users WHERE id = ?",
                (uid,),
            ).fetchone()
        )

        if user_exists and body:
            db.execute(
                """
                INSERT INTO messages (
                    user_id,
                    author_role,
                    body
                )
                VALUES (?, ?, ?)
                """,
                (
                    uid,
                    "cabinet",
                    body,
                ),
            )

            db.commit()

        return redirect(url_for("cabinet") + "#messages")

    # =====================================================
    # DÉCONNEXION
    # =====================================================

    @app.post("/deconnexion")
    def logout():
        require_csrf()

        session.clear()

        flash("Vous avez été déconnecté.", "success")

        return redirect(url_for("portal"))

    return app
