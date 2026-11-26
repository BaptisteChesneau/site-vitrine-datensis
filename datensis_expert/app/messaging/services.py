"""Services de messagerie sécurisée DATENSIS Expert."""

import sqlite3

from app import protect, reveal, utc_now

MAX_MESSAGE_LENGTH = 2000
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 100

ALLOWED_ROLES = {"client", "cabinet"}


# =====================================================
# VALIDATION
# =====================================================


def validate_role(role: str) -> None:
    if role not in ALLOWED_ROLES:
        raise ValueError("Rôle de messagerie invalide.")


def client_exists(
    db: sqlite3.Connection,
    user_id: int,
) -> bool:
    return (
        db.execute(
            "SELECT 1 FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        is not None
    )


def validate_message(body: str) -> str:
    if not isinstance(body, str):
        raise TypeError("Format du message invalide.")

    body = body.strip()

    if not body:
        raise ValueError("Le message est vide.")

    if len(body) > MAX_MESSAGE_LENGTH:
        raise ValueError("Le message ne doit pas dépasser 2000 caractères.")

    return body


# =====================================================
# SERIALISATION
# =====================================================


def serialize_message(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "author_role": row["author_role"],
        "author_admin_id": row["author_admin_id"],
        "body": reveal(row["body"]),
        "created_at": row["created_at"],
        "read_at": row["read_at"],
        "is_read": row["read_at"] is not None,
    }


# =====================================================
# RECUPERATION DES MESSAGES
# =====================================================


def get_messages(
    db: sqlite3.Connection,
    user_id: int,
    *,
    limit: int = DEFAULT_PAGE_SIZE,
    before_id: int | None = None,
    after_id: int | None = None,
) -> dict:
    limit = max(1, min(limit, MAX_PAGE_SIZE))

    if before_id is not None and after_id is not None:
        raise ValueError("Pagination incompatible.")

    if before_id is not None:
        rows = db.execute(
            """
            SELECT *
            FROM messages
            WHERE user_id = ? AND id < ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (user_id, before_id, limit + 1),
        ).fetchall()

    elif after_id is not None:
        rows = db.execute(
            """
            SELECT *
            FROM messages
            WHERE user_id = ? AND id > ?
            ORDER BY id ASC
            LIMIT ?
            """,
            (user_id, after_id, limit + 1),
        ).fetchall()

    else:
        rows = db.execute(
            """
            SELECT *
            FROM messages
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (user_id, limit + 1),
        ).fetchall()

    has_more = len(rows) > limit
    rows = rows[:limit]

    if after_id is None:
        rows = list(reversed(rows))

    messages = [serialize_message(row) for row in rows]

    return {
        "messages": messages,
        "has_more": has_more,
        "oldest_id": messages[0]["id"] if messages else None,
        "latest_id": messages[-1]["id"] if messages else None,
    }


# =====================================================
# ENVOI D'UN MESSAGE
# =====================================================


def send_message(
    db: sqlite3.Connection,
    user_id: int,
    author_role: str,
    body: str,
    *,
    admin_id: int | None = None,
) -> dict:
    validate_role(author_role)
    body = validate_message(body)

    if not client_exists(db, user_id):
        raise LookupError("Client introuvable.")

    if author_role == "client":
        admin_id = None

    elif (
        admin_id is None
        or not db.execute(
            "SELECT 1 FROM cabinet_admins WHERE id = ?",
            (admin_id,),
        ).fetchone()
    ):
        raise ValueError("Collaborateur invalide.")

    try:
        cursor = db.execute(
            """
            INSERT INTO messages (
                user_id,
                author_role,
                author_admin_id,
                body,
                created_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                user_id,
                author_role,
                admin_id,
                protect(body),
                utc_now().strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )

        row = db.execute(
            """
            SELECT *
            FROM messages
            WHERE id = ? AND user_id = ?
            """,
            (cursor.lastrowid, user_id),
        ).fetchone()

        message = serialize_message(row)

        db.commit()

        return message

    except Exception:
        db.rollback()
        raise


# =====================================================
# ACCUSES DE LECTURE
# =====================================================


def mark_messages_as_read(
    db: sqlite3.Connection,
    user_id: int,
    reader_role: str,
    up_to_id: int,
) -> int:
    validate_role(reader_role)

    if up_to_id <= 0:
        raise ValueError("Identifiant de message invalide.")

    sender_role = "cabinet" if reader_role == "client" else "client"

    try:
        cursor = db.execute(
            """
            UPDATE messages
            SET read_at = ?
            WHERE user_id = ?
              AND author_role = ?
              AND read_at IS NULL
              AND id <= ?
            """,
            (
                utc_now().isoformat(),
                user_id,
                sender_role,
                up_to_id,
            ),
        )

        db.commit()

        return cursor.rowcount

    except Exception:
        db.rollback()
        raise


# =====================================================
# MESSAGES NON LUS
# =====================================================


def count_unread_messages(
    db: sqlite3.Connection,
    reader_role: str,
    user_id: int | None = None,
) -> int:
    validate_role(reader_role)

    sender_role = "cabinet" if reader_role == "client" else "client"

    if reader_role == "client" and user_id is None:
        raise ValueError("Identifiant client obligatoire.")

    if user_id is None:
        row = db.execute(
            """
            SELECT COUNT(*) AS total
            FROM messages
            WHERE author_role = ?
              AND read_at IS NULL
            """,
            (sender_role,),
        ).fetchone()

    else:
        row = db.execute(
            """
            SELECT COUNT(*) AS total
            FROM messages
            WHERE user_id = ?
              AND author_role = ?
              AND read_at IS NULL
            """,
            (user_id, sender_role),
        ).fetchone()

    return int(row["total"])


# =====================================================
# CONVERSATIONS CABINET
# =====================================================


def get_conversations(
    db: sqlite3.Connection,
) -> list[dict]:
    rows = db.execute(
        """
        SELECT
            u.id AS user_id,
            u.name,
            u.company_name,
            m.id AS last_message_id,
            m.body AS last_message,
            m.author_role AS last_author_role,
            m.created_at AS last_message_at,
            (
                SELECT COUNT(*)
                FROM messages AS unread
                WHERE unread.user_id = u.id
                  AND unread.author_role = 'client'
                  AND unread.read_at IS NULL
            ) AS unread_count
        FROM users AS u
        LEFT JOIN messages AS m
            ON m.id = (
                SELECT MAX(latest.id)
                FROM messages AS latest
                WHERE latest.user_id = u.id
            )
        ORDER BY
            COALESCE(m.id, 0) DESC,
            u.id DESC
        """
    ).fetchall()

    conversations = []

    for row in rows:
        conversations.append(
            {
                "user_id": row["user_id"],
                "name": reveal(row["name"]),
                "company_name": reveal(row["company_name"]),
                "last_message_id": row["last_message_id"],
                "last_message": (
                    reveal(row["last_message"])
                    if row["last_message"] is not None
                    else None
                ),
                "last_author_role": row["last_author_role"],
                "last_message_at": row["last_message_at"],
                "unread_count": row["unread_count"],
            }
        )

    return conversations
