"""One-time encryption migration. Stop Flask, back up DB, then run this script."""

import sqlite3
from datetime import datetime, timezone

from app import DB, PERSONAL_FIELDS, email_index, init_database, protect, reveal


def migrate():
    init_database()

    if not DB.exists():
        raise SystemExit("Base SQLite introuvable")

    backup = DB.with_name(
        f"expert.backup-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}.sqlite3"
    )

    with sqlite3.connect(DB) as source, sqlite3.connect(backup) as destination:
        source.backup(destination)

    print(f"Sauvegarde créée : {backup}")

    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row

    try:
        db.execute("BEGIN IMMEDIATE")

        # Tables utilisateurs : requêtes SQL fixes
        user_tables = {
            "users": {
                "columns": "PRAGMA table_info(users)",
                "select": "SELECT * FROM users",
                "update": "UPDATE users SET {assignments} WHERE id = ?",
            },
            "cabinet_admins": {
                "columns": "PRAGMA table_info(cabinet_admins)",
                "select": "SELECT * FROM cabinet_admins",
                "update": "UPDATE cabinet_admins SET {assignments} WHERE id = ?",
            },
        }

        for config in user_tables.values():
            cols = {row[1] for row in db.execute(config["columns"])}

            fields = [field for field in PERSONAL_FIELDS if field in cols]

            # Validation stricte des noms de colonnes
            allowed_fields = {
                "name",
                "email",
                "phone",
                "company",
                "first_name",
                "last_name",
            }

            fields = [field for field in fields if field in allowed_fields]

            for row in db.execute(config["select"]).fetchall():
                if row["email_index"] is not None:
                    continue

                email = reveal(row["email"])

                changes = {field: protect(reveal(row[field])) for field in fields}

                changes["email_index"] = email_index(email)

                assignments = ", ".join(f"{field} = ?" for field in changes)

                query = config["update"].format(assignments=assignments)

                db.execute(
                    query,
                    (*changes.values(), row["id"]),
                )

        # Documents : chiffrement des titres
        for row in db.execute("SELECT id, title FROM documents").fetchall():
            value = row["title"]

            if value is not None and not str(value).startswith("enc:v1:"):
                db.execute(
                    "UPDATE documents SET title = ? WHERE id = ?",
                    (protect(value), row["id"]),
                )

        # Messages : chiffrement du contenu
        for row in db.execute("SELECT id, body FROM messages").fetchall():
            value = row["body"]

            if value is not None and not str(value).startswith("enc:v1:"):
                db.execute(
                    "UPDATE messages SET body = ? WHERE id = ?",
                    (protect(value), row["id"]),
                )

        db.commit()

    except Exception:
        db.rollback()
        print("Échec : transaction annulée. Restaurer la sauvegarde si nécessaire.")
        raise

    finally:
        db.close()

    print("Migration terminée. Conservez la sauvegarde dans un lieu sécurisé.")


if __name__ == "__main__":
    migrate()
