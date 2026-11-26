"""Migration non destructive de la messagerie DATENSIS Expert."""

import sqlite3


def migrate_messages(db: sqlite3.Connection) -> None:
    """Ajoute les fonctionnalités de messagerie à la base existante."""

    db.execute("BEGIN IMMEDIATE")

    try:
        columns = {row[1] for row in db.execute("PRAGMA table_info(messages)")}

        if not columns:
            raise RuntimeError(
                "La table messages doit être initialisée avant la migration."
            )

        # Date de lecture du message.
        if "read_at" not in columns:
            db.execute("ALTER TABLE messages ADD COLUMN read_at TEXT")

        # Identification du collaborateur expéditeur.
        if "author_admin_id" not in columns:
            db.execute(
                "ALTER TABLE messages "
                "ADD COLUMN author_admin_id INTEGER "
                "REFERENCES cabinet_admins(id)"
            )

        # Optimisation de la récupération des conversations.
        db.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_user_id
            ON messages(user_id, id)
        """)

        # Optimisation du compteur de messages non lus.
        db.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_unread
            ON messages(user_id, author_role, read_at)
        """)

        db.commit()

    except Exception:
        db.rollback()
        raise
