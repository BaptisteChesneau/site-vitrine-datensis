import base64
import hashlib
import hmac
import io
import logging
import os
import re
import secrets
import smtplib
import sqlite3
import time
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from functools import wraps
from pathlib import Path

import pyotp
import qrcode
from argon2 import PasswordHasher
from argon2 import exceptions as argon_errors
from cryptography.fernet import Fernet, InvalidToken
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
)

BASE = Path(__file__).resolve().parent.parent

load_dotenv(BASE / ".env")

DB = BASE / "instance" / "expert.sqlite3"

LOGGER = logging.getLogger(__name__)

# Encryption keys are independent of Flask's SECRET_KEY.

# Configure before starting the app; never commit them to Git.


def _security_keys():
    encryption = os.environ.get("DATENSIS_DATA_KEY", "").strip()

    index_key = os.environ.get("DATENSIS_INDEX_KEY", "").strip()

    if not encryption or len(index_key) < 32:
        raise RuntimeError("DATENSIS_DATA_KEY et DATENSIS_INDEX_KEY requis dans .env")

    try:
        cipher = Fernet(encryption.encode("ascii"))

    except (ValueError, TypeError) as exc:
        raise RuntimeError("DATENSIS_DATA_KEY invalide") from exc

    return cipher, index_key.encode("utf-8")


CIPHER, INDEX_KEY = _security_keys()

PASSWORD_HASHER = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)

PERSONAL_FIELDS = (
    "name",
    "email",
    "phone",
    "first_name",
    "last_name",
    "company_name",
    "siret",
    "legal_form",
    "activity",
    "address",
    "postal_code",
    "city",
    "country",
)


def protect(value):
    if value is None:
        return None

    value = str(value)

    if value.startswith("enc:v1:"):
        raise ValueError("Refus de chiffrer deux fois")

    return "enc:v1:" + CIPHER.encrypt(value.encode("utf-8")).decode("ascii")


def reveal(value):
    if not isinstance(value, str) or not value.startswith("enc:v1:"):
        return value

    try:
        return CIPHER.decrypt(value[7:].encode("ascii")).decode("utf-8")

    except InvalidToken as exc:
        raise RuntimeError(
            "Donnée chiffrée illisible : clé incorrecte ou données altérées"
        ) from exc


def otp_digest(value):
    return hmac.new(INDEX_KEY, value.encode("utf-8"), hashlib.sha256).hexdigest()


def otp_record(db, role, account_id):
    return db.execute(
        "SELECT * FROM totp_accounts WHERE account_role = ? AND account_id = ?",
        (role, account_id),
    ).fetchone()


def otp_valid(secret, code):
    return bool(re.fullmatch(r"[0-9]{6}", code)) and pyotp.TOTP(secret).verify(
        code, valid_window=1
    )


def otp_counter(secret, code):
    if not re.fullmatch(r"[0-9]{6}", code):
        return None
    now = int(time.time()) // 30
    totp = pyotp.TOTP(secret)
    for counter in (now - 1, now, now + 1):
        if hmac.compare_digest(totp.at(counter * 30), code):
            return counter
    return None


def otp_backup_codes(db, role, account_id):
    codes = [secrets.token_hex(5).upper() for _ in range(8)]
    db.execute(
        "DELETE FROM totp_recovery WHERE account_role = ? AND account_id = ?",
        (role, account_id),
    )
    db.executemany(
        "INSERT INTO totp_recovery (account_role, account_id, code_hash) VALUES (?, ?, ?)",
        [(role, account_id, otp_digest(code)) for code in codes],
    )
    return codes


def otp_qr_data(uri):
    img = qrcode.make(uri)
    stream = io.BytesIO()
    img.save(stream, format="PNG")
    return "data:image/png;base64," + base64.b64encode(stream.getvalue()).decode(
        "ascii"
    )


def otp_finish_login(db, role, account_id):
    if role == "cabinet":
        account = db.execute(
            "SELECT id, name FROM cabinet_admins WHERE id = ?", (account_id,)
        ).fetchone()
    elif role == "client":
        account = db.execute(
            "SELECT id, name FROM users WHERE id = ?", (account_id,)
        ).fetchone()
    else:
        session.clear()
        abort(403)
    if account is None:
        session.clear()
        abort(403)
    session.clear()
    session.permanent = True
    session.update(role=role, name=reveal(account["name"]))
    if role == "cabinet":
        session["admin_id"] = account_id
    else:
        session["user_id"] = account_id
    return redirect(url_for("cabinet" if role == "cabinet" else "client"))


def email_index(email):
    normalized = email.strip().casefold()

    return hmac.new(INDEX_KEY, normalized.encode("utf-8"), hashlib.sha256).hexdigest()


def public_row(row, fields=PERSONAL_FIELDS):
    if row is None:
        return None

    data = dict(row)

    for field in fields:
        if field in data:
            data[field] = reveal(data[field])

    return data


def public_rows(rows, fields=PERSONAL_FIELDS):
    return [public_row(row, fields) for row in rows]


def hash_password(password):
    return PASSWORD_HASHER.hash(password)


def verify_password(stored, password):
    if not isinstance(stored, str) or not stored or not password:
        return False

    if stored.startswith("$argon2id$"):
        try:
            return PASSWORD_HASHER.verify(stored, password)

        except (
            argon_errors.VerifyMismatchError,
            argon_errors.VerificationError,
            argon_errors.InvalidHashError,
        ):
            return False

    try:
        return check_password_hash(stored, password)

    except (ValueError, TypeError):
        return False


def upgrade_password(db, table, row, password):
    if table not in {"users", "cabinet_admins"}:
        raise ValueError("Table non autorisée")

    stored_hash = row["password_hash"]
    needs_upgrade = not stored_hash.startswith("$argon2id$")
    if not needs_upgrade:
        needs_upgrade = PASSWORD_HASHER.check_needs_rehash(stored_hash)
    if not needs_upgrade:
        return

    new_hash = hash_password(password)
    if table == "users":
        db.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (new_hash, row["id"]),
        )
    else:
        db.execute(
            "UPDATE cabinet_admins SET password_hash = ? WHERE id = ?",
            (new_hash, row["id"]),
        )
    db.commit()


def account_by_email(db, table, email):
    indexed_email = email_index(email)
    if table == "users":
        return db.execute(
            "SELECT * FROM users WHERE email_index = ?", (indexed_email,)
        ).fetchone()
    if table == "cabinet_admins":
        return db.execute(
            "SELECT * FROM cabinet_admins WHERE email_index = ?", (indexed_email,)
        ).fetchone()
    raise ValueError("Table non autorisée")


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
        LOGGER.warning(
            "CSRF invalide : endpoint=%s, "
            "jeton_formulaire_present=%s, "
            "jeton_session_present=%s",
            request.endpoint,
            bool(submitted),
            bool(expected),
        )
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
        isinstance(value, str)
        and len(value) <= 254
        and bool(
            re.fullmatch(
                r"[^@\s]+@[^@\s]+\.[^@\s]+",
                value,
            )
        )
    )


def phone_valid(value):
    return bool(re.fullmatch(r"[+0-9(). /-]{6,30}", value))


def utc_now():
    return datetime.now(UTC)


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

            CREATE TABLE IF NOT EXISTS cabinet_admins (

                  id INTEGER PRIMARY KEY,

                  name TEXT NOT NULL,

                  email TEXT NOT NULL UNIQUE COLLATE NOCASE,

                  password_hash TEXT NOT NULL,

                  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP

              );

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

        db.executescript("""
            CREATE TABLE IF NOT EXISTS totp_accounts (
                account_role TEXT NOT NULL CHECK(account_role IN ('client', 'cabinet')),
                account_id INTEGER NOT NULL,
                secret_enc TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 0,
                last_counter INTEGER NOT NULL DEFAULT -1,
                PRIMARY KEY (account_role, account_id)
            );
            CREATE TABLE IF NOT EXISTS totp_recovery_display (
                token_hash TEXT PRIMARY KEY,
                codes_enc TEXT NOT NULL,
                expires_at INTEGER NOT NULL,
                account_role TEXT NOT NULL,
                account_id INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS totp_recovery (
                account_role TEXT NOT NULL,
                account_id INTEGER NOT NULL,
                code_hash TEXT NOT NULL,
                PRIMARY KEY (account_role, account_id, code_hash)
            );
        """)

        columns = {row[1] for row in db.execute("PRAGMA table_info(users)")}

        for column, definition in USER_COLUMNS:
            if column not in columns:
                db.execute(f"ALTER TABLE users ADD COLUMN {column} {definition}")

        for table in ("users", "cabinet_admins"):
            existing = {row[1] for row in db.execute(f"PRAGMA table_info({table})")}

            if "email_index" not in existing:
                db.execute(f"ALTER TABLE {table} ADD COLUMN email_index TEXT")

            db.execute(
                f"CREATE UNIQUE INDEX IF NOT EXISTS idx_{table}_email_index ON {table}(email_index)"
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
        raise RuntimeError("SECRET_KEY doit contenir au moins 32 caractères dans .env")

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

    with sqlite3.connect(DB) as security_db:
        checks = (
            ("users", "SELECT COUNT(*) FROM users WHERE email_index IS NULL"),
            (
                "cabinet_admins",
                "SELECT COUNT(*) FROM cabinet_admins WHERE email_index IS NULL",
            ),
        )
        for table, query in checks:
            unmigrated = security_db.execute(query).fetchone()[0]
            if unmigrated:
                raise RuntimeError(
                    f"{unmigrated} compte(s) {table} à migrer : "
                    "lancer migrate_security.py avant Flask"
                )

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

            db = database()
            user = account_by_email(db, "users", email)

            if user and verify_password(user["password_hash"], password):
                upgrade_password(db, "users", user, password)

                otp = otp_record(db, "client", user["id"])

                # Créer une session temporaire avant la 2FA.
                session.clear()
                session.permanent = True
                session.update(
                    pending_role="client",
                    pending_id=user["id"],
                    pending_at=int(time.time()),
                    otp_attempts=0,
                )

                # 2FA déjà activée : demander le code.
                if otp and otp["enabled"]:
                    return redirect(url_for("otp_challenge"))

                # Première connexion : afficher le QR code.
                return redirect(url_for("otp_setup"))

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
                errors.append("Vous devez accepter les conditions d'utilisation.")

            if errors:
                for error in dict.fromkeys(errors):
                    flash(error, "error")

                return render_template("register.html"), 400

            name = f"{values['first_name']} {values['last_name']}"

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

                        country,

                        email_index

                    )

                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)

                    """,
                    (
                        protect(name),
                        protect(email),
                        hash_password(password),
                        protect(values["first_name"]),
                        protect(values["last_name"]),
                        protect(values["phone"]),
                        protect(values["company_name"]),
                        protect(values["siret"]),
                        protect(values["legal_form"]),
                        protect(values["activity"]),
                        protect(values["address"]),
                        protect(values["postal_code"]),
                        protect(values["city"]),
                        protect(values["country"] or "France"),
                        email_index(email),
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

            user = account_by_email(db, "users", email)

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
                        hash_password(password),
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
                "Votre mot de passe a été modifié. Vous pouvez vous connecter.",
                "success",
            )

            return redirect(url_for("portal"))

        return render_template("reset_password.html")

    # =====================================================

    # CONNEXION CABINET

    # =====================================================

    @app.route("/cabinet/connexion", methods=["GET", "POST"])
    def cabinet_login():
        if session.get("role") == "cabinet":
            return redirect(url_for("cabinet"))

        if request.method == "POST":
            require_csrf()

            email = request.form.get("email", "").strip().lower()

            password = request.form.get("password", "")

            admin = None

            if email_valid(email) and password:
                admin = account_by_email(database(), "cabinet_admins", email)

            if admin and verify_password(admin["password_hash"], password):
                upgrade_password(database(), "cabinet_admins", admin, password)

                session.clear()
                session.update(
                    pending_role="cabinet",
                    pending_id=admin["id"],
                    pending_at=int(time.time()),
                    otp_attempts=0,
                )
                otp = otp_record(database(), "cabinet", admin["id"])
                return redirect(
                    url_for("otp_challenge" if otp and otp["enabled"] else "otp_setup")
                )

            flash("Adresse e-mail ou mot de passe incorrect.", "error")

            return render_template("cabinet_login.html"), 401

        return render_template("cabinet_login.html")

    # =====================================================

    # =====================================================

    # ESPACE CLIENT

    # =====================================================

    def otp_identity():
        role = session.get("pending_role")
        account_id = session.get("pending_id")
        since = session.get("pending_at", 0)
        if (
            role not in ("client", "cabinet")
            or not isinstance(account_id, int)
            or int(time.time()) - since > 300
        ):
            session.clear()
            return None
        return role, account_id

    @app.route("/auth/2fa", methods=["GET", "POST"])
    def otp_challenge():
        identity = otp_identity()
        if not identity:
            return redirect(url_for("portal"))
        role, account_id = identity
        db = database()
        record = otp_record(db, role, account_id)
        if not record or not record["enabled"]:
            return (
                redirect(url_for("otp_setup"))
                if role == "cabinet"
                else redirect(url_for("portal"))
            )
        if request.method == "POST":
            require_csrf()
            attempts = session.get("otp_attempts", 0) + 1
            session["otp_attempts"] = attempts
            if attempts > 5:
                session.clear()
                abort(429, "Trop de tentatives. Reconnectez-vous.")
            code = request.form.get("code", "").strip().replace("-", "").upper()
            counter = otp_counter(reveal(record["secret_enc"]), code)
            if counter is not None:
                claimed = db.execute(
                    "UPDATE totp_accounts SET last_counter = ? WHERE account_role = ? AND account_id = ? AND last_counter < ?",
                    (counter, role, account_id, counter),
                )
                db.commit()
                if claimed.rowcount == 1:
                    return otp_finish_login(db, role, account_id)
            else:
                matched = db.execute(
                    "DELETE FROM totp_recovery WHERE account_role = ? AND account_id = ? AND code_hash = ?",
                    (role, account_id, otp_digest(code)),
                )
                db.commit()
                if matched.rowcount == 1:
                    return otp_finish_login(db, role, account_id)
            flash("Code invalide ou déjà utilisé.", "error")
        return render_template("otp_challenge.html")

    @app.route("/auth/2fa/configurer", methods=["GET", "POST"])
    def otp_setup():
        identity = otp_identity()
        if not identity:
            if session.get("role") == "client":
                identity = ("client", session["user_id"])
            else:
                return redirect(url_for("portal"))
        role, account_id = identity
        db = database()
        record = otp_record(db, role, account_id)
        if record and record["enabled"]:
            return (
                redirect(url_for("otp_challenge"))
                if session.get("pending_role")
                else redirect(url_for("client"))
            )
        if not record:
            secret = pyotp.random_base32()
            db.execute(
                "INSERT INTO totp_accounts(account_role, account_id, secret_enc) VALUES (?, ?, ?)",
                (role, account_id, protect(secret)),
            )
            db.commit()
        else:
            secret = reveal(record["secret_enc"])
        if request.method == "POST":
            require_csrf()
            attempts = session.get("otp_setup_attempts", 0) + 1
            session["otp_setup_attempts"] = attempts
            if attempts > 5:
                session.clear()
                abort(429)
            code = request.form.get("code", "").strip()
            if otp_valid(secret, code):
                counter = otp_counter(secret, code)
                db.execute(
                    "UPDATE totp_accounts SET enabled = 1, last_counter = ? WHERE account_role = ? AND account_id = ? AND enabled = 0",
                    (counter, role, account_id),
                )
                codes = otp_backup_codes(db, role, account_id)
                db.commit()
                session.pop("otp_setup_attempts", None)
                display_token = secrets.token_urlsafe(32)
                db.execute(
                    "INSERT INTO totp_recovery_display(token_hash, codes_enc, expires_at, account_role, account_id) VALUES (?, ?, ?, ?, ?)",
                    (
                        token_hash(display_token),
                        protect("\n".join(codes)),
                        int(time.time()) + 300,
                        role,
                        account_id,
                    ),
                )
                db.commit()
                session["otp_display_token"] = display_token
                return redirect(url_for("otp_recovery_display"))
            flash("Code incorrect.", "error")
        if role == "cabinet":
            account = db.execute(
                "SELECT email FROM cabinet_admins WHERE id = ?", (account_id,)
            ).fetchone()
        elif role == "client":
            account = db.execute(
                "SELECT email FROM users WHERE id = ?", (account_id,)
            ).fetchone()
        else:
            abort(403)
        if account is None:
            abort(403)
        uri = pyotp.TOTP(secret).provisioning_uri(
            name=reveal(account["email"]), issuer_name="DATENSIS Expert"
        )
        return render_template(
            "otp_setup.html", qr_data=otp_qr_data(uri), secret=secret
        )

    @app.route("/auth/2fa/recuperation", methods=["GET", "POST"])
    def otp_recovery_display():
        display_token = session.get("otp_display_token")
        if not display_token:
            abort(404)
        db = database()
        display = db.execute(
            "SELECT * FROM totp_recovery_display WHERE token_hash = ? AND expires_at > ?",
            (token_hash(display_token), int(time.time())),
        ).fetchone()
        if display is None:
            session.pop("otp_display_token", None)
            abort(404)
        role, account_id = display["account_role"], display["account_id"]
        pending = otp_identity() if session.get("pending_role") else None
        authenticated_id = (
            session.get("admin_id") if role == "cabinet" else session.get("user_id")
        )
        if pending != (role, account_id) and not (
            session.get("role") == role and authenticated_id == account_id
        ):
            abort(403)
        if request.method == "POST":
            require_csrf()
            db.execute(
                "DELETE FROM totp_recovery_display WHERE token_hash = ?",
                (token_hash(display_token),),
            )
            db.commit()
            session.pop("otp_display_token", None)
            if pending == (role, account_id):
                return otp_finish_login(db, role, account_id)
            return redirect(url_for("client" if role == "client" else "cabinet"))
        return render_template(
            "otp_recovery.html", codes=reveal(display["codes_enc"]).split("\n")
        )

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

        user = public_row(user)

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

        docs = public_rows(docs, ("title",))

        messages = public_rows(messages, ("body",))

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

        values = [int(request.form.get(name) == "1") for name in names]

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
                (protect(name), protect(phone), session["user_id"]),
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

        if not user or not verify_password(user["password_hash"], old):
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
                    hash_password(new),
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
                (session["user_id"], protect(title)),
            )

            db.commit()

            flash(
                "Référence documentaire enregistrée. Aucun fichier n'a été transféré.",
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
                    protect(body),
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

        users = public_rows(users)

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

        docs = public_rows(docs, ("title", "client_name"))

        messages = public_rows(messages, ("body", "client_name"))

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
                    protect(body),
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
