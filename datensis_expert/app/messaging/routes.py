"""Routes API de la messagerie DATENSIS Expert."""

import secrets
from functools import wraps

from flask import jsonify, request, session

from .. import database
from . import messaging_bp
from .services import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    client_exists,
    count_unread_messages,
    get_conversations,
    get_messages,
    mark_messages_as_read,
    send_message,
)

# =====================================================
# REPONSES JSON
# =====================================================


def api_success(data=None, status=200):
    return jsonify(
        {
            "success": True,
            "data": data,
        }
    ), status


def api_error(message, status=400):
    return jsonify(
        {
            "success": False,
            "error": message,
        }
    ), status


# =====================================================
# AUTHENTIFICATION ET AUTORISATIONS
# =====================================================


def api_role_required(role):
    """Controle la session et les droits d'acces."""

    def decorator(function):
        @wraps(function)
        def wrapper(*args, **kwargs):
            if session.get("role") not in {
                "client",
                "cabinet",
            }:
                return api_error(
                    "Authentification requise.",
                    401,
                )

            if session.get("role") != role:
                return api_error(
                    "Acces non autorise.",
                    403,
                )

            account_id = session.get("admin_id" if role == "cabinet" else "user_id")

            version = session.get("session_version")

            if type(account_id) is not int:
                session.clear()

                return api_error(
                    "Session invalide.",
                    401,
                )

            db = database()

            if role == "cabinet":
                account = db.execute(
                    """
                    SELECT session_version
                    FROM cabinet_admins
                    WHERE id = ?
                    """,
                    (account_id,),
                ).fetchone()

            else:
                account = db.execute(
                    """
                    SELECT session_version
                    FROM users
                    WHERE id = ?
                    """,
                    (account_id,),
                ).fetchone()

            if account is None or version != account["session_version"]:
                session.clear()

                return api_error(
                    "Session expiree.",
                    401,
                )

            return function(*args, **kwargs)

        return wrapper

    return decorator


# =====================================================
# PROTECTION CSRF
# =====================================================


def api_csrf_required(function):
    """Controle le jeton CSRF des requetes API."""

    @wraps(function)
    def wrapper(*args, **kwargs):
        submitted = request.headers.get(
            "X-CSRF-Token",
            "",
        )

        expected = session.get("csrf", "")

        if (
            not submitted
            or not expected
            or not submitted.isascii()
            or not secrets.compare_digest(
                submitted,
                expected,
            )
        ):
            return api_error(
                "Jeton CSRF invalide.",
                403,
            )

        return function(*args, **kwargs)

    return wrapper


# =====================================================
# VALIDATION DES REQUETES
# =====================================================


def get_json_payload():
    """Recupere uniquement un objet JSON valide."""

    if not request.is_json:
        return None

    payload = request.get_json(silent=True)

    if not isinstance(payload, dict):
        return None

    return payload


def get_pagination():
    """Valide les parametres de pagination."""

    limit = request.args.get(
        "limit",
        str(DEFAULT_PAGE_SIZE),
    )

    before_id = request.args.get("before_id")
    after_id = request.args.get("after_id")

    limit = int(limit)

    if not 1 <= limit <= MAX_PAGE_SIZE:
        raise ValueError("Limite invalide.")

    if before_id is not None:
        before_id = int(before_id)

        if before_id <= 0:
            raise ValueError("Identifiant de pagination invalide.")

    if after_id is not None:
        after_id = int(after_id)

        if after_id < 0:
            raise ValueError("Identifiant de pagination invalide.")

    if before_id is not None and after_id is not None:
        raise ValueError("Pagination incompatible.")

    if before_id is not None and before_id > 9223372036854775807:
        raise ValueError("Identifiant de pagination invalide.")

    if after_id is not None and after_id > 9223372036854775807:
        raise ValueError("Identifiant de pagination invalide.")

    return {
        "limit": limit,
        "before_id": before_id,
        "after_id": after_id,
    }


# =====================================================
# OPERATIONS COMMUNES
# =====================================================


def conversation_response(user_id):
    db = database()

    if not client_exists(db, user_id):
        return api_error(
            "Client introuvable.",
            404,
        )

    try:
        pagination = get_pagination()

        result = get_messages(
            db,
            user_id,
            **pagination,
        )

    except ValueError:
        return api_error(
            "Parametres de pagination invalides.",
            400,
        )

    return api_success(result)


def send_message_response(
    user_id,
    author_role,
    admin_id=None,
):
    payload = get_json_payload()

    if payload is None:
        return api_error(
            "Corps JSON invalide.",
            400,
        )

    try:
        message = send_message(
            database(),
            user_id,
            author_role,
            payload.get("body"),
            admin_id=admin_id,
        )

    except (TypeError, ValueError) as exc:
        return api_error(str(exc), 400)

    except LookupError:
        return api_error(
            "Client introuvable.",
            404,
        )

    return api_success(message, 201)


def read_messages_response(
    user_id,
    reader_role,
):
    payload = get_json_payload()

    if payload is None:
        return api_error(
            "Corps JSON invalide.",
            400,
        )

    up_to_id = payload.get("up_to_id")

    if type(up_to_id) is not int or not 1 <= up_to_id <= 9223372036854775807:
        return api_error(
            "Identifiant de message invalide.",
            400,
        )

    db = database()

    if not client_exists(db, user_id):
        return api_error(
            "Client introuvable.",
            404,
        )

    message = db.execute(
        """
        SELECT id
        FROM messages
        WHERE id = ?
          AND user_id = ?
        """,
        (up_to_id, user_id),
    ).fetchone()

    if message is None:
        return api_error(
            "Message introuvable.",
            404,
        )

    updated = mark_messages_as_read(
        db,
        user_id,
        reader_role,
        up_to_id,
    )

    unread = count_unread_messages(
        db,
        reader_role,
        user_id,
    )

    return api_success(
        {
            "updated": updated,
            "unread_count": unread,
        }
    )


# =====================================================
# API CLIENT - RECUPERATION DES MESSAGES
# =====================================================


@messaging_bp.get("/client/messages")
@api_role_required("client")
def client_get_messages():
    return conversation_response(
        session["user_id"],
    )


# =====================================================
# API CLIENT - ENVOI D'UN MESSAGE
# =====================================================


@messaging_bp.post("/client/messages")
@api_role_required("client")
@api_csrf_required
def client_send_message():
    return send_message_response(
        session["user_id"],
        "client",
    )


# =====================================================
# API CLIENT - ACCUSES DE LECTURE
# =====================================================


@messaging_bp.post("/client/messages/read")
@api_role_required("client")
@api_csrf_required
def client_read_messages():
    return read_messages_response(
        session["user_id"],
        "client",
    )


# =====================================================
# API CLIENT - MESSAGES NON LUS
# =====================================================


@messaging_bp.get("/client/messages/unread")
@api_role_required("client")
def client_unread_messages():
    unread = count_unread_messages(
        database(),
        "client",
        session["user_id"],
    )

    return api_success(
        {
            "unread_count": unread,
        }
    )


# =====================================================
# API CABINET - LISTE DES CONVERSATIONS
# =====================================================


@messaging_bp.get("/cabinet/conversations")
@api_role_required("cabinet")
def cabinet_conversations():
    conversations = get_conversations(
        database(),
    )

    return api_success(
        {
            "conversations": conversations,
        }
    )


# =====================================================
# API CABINET - RECUPERATION DES MESSAGES
# =====================================================


@messaging_bp.get("/cabinet/messages/<int:user_id>")
@api_role_required("cabinet")
def cabinet_get_messages(user_id):
    if not 1 <= user_id <= 9223372036854775807:
        return api_error(
            "Client introuvable.",
            404,
        )

    return conversation_response(user_id)


# =====================================================
# API CABINET - ENVOI D'UN MESSAGE
# =====================================================


@messaging_bp.post("/cabinet/messages/<int:user_id>")
@api_role_required("cabinet")
@api_csrf_required
def cabinet_send_message(user_id):
    if not 1 <= user_id <= 9223372036854775807:
        return api_error(
            "Client introuvable.",
            404,
        )

    return send_message_response(
        user_id,
        "cabinet",
        admin_id=session["admin_id"],
    )


# =====================================================
# API CABINET - ACCUSES DE LECTURE
# =====================================================


@messaging_bp.post("/cabinet/messages/<int:user_id>/read")
@api_role_required("cabinet")
@api_csrf_required
def cabinet_read_messages(user_id):
    if not 1 <= user_id <= 9223372036854775807:
        return api_error(
            "Client introuvable.",
            404,
        )

    return read_messages_response(
        user_id,
        "cabinet",
    )


# =====================================================
# API CABINET - MESSAGES NON LUS
# =====================================================


@messaging_bp.get("/cabinet/messages/unread")
@api_role_required("cabinet")
def cabinet_unread_messages():
    unread = count_unread_messages(
        database(),
        "cabinet",
    )

    return api_success(
        {
            "unread_count": unread,
        }
    )
