import sqlite3
import time

import pyotp
import pytest

TEST_PASSWORD = "Datensis-Test-2026!Secure"
TEST_EMAIL = "auth-test@example.com"
CSRF = "csrf-auth-flow-test"


@pytest.fixture
def test_account(app):
    from app import DB, email_index, hash_password, protect

    with sqlite3.connect(DB) as db:
        cursor = db.execute(
            """
            INSERT INTO users (
                name,
                email,
                email_index,
                password_hash
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                protect("Client Test"),
                protect(TEST_EMAIL),
                email_index(TEST_EMAIL),
                hash_password(TEST_PASSWORD),
            ),
        )
        account_id = cursor.lastrowid
        db.commit()

    return account_id


@pytest.fixture
def test_cabinet_account(app):
    from app import DB, email_index, hash_password, protect

    email = "cabinet-test@datensis.fr"

    with sqlite3.connect(DB) as db:
        cursor = db.execute(
            """
            INSERT INTO cabinet_admins (
                name,
                email,
                email_index,
                password_hash
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                protect("Cabinet Test"),
                protect(email),
                email_index(email),
                hash_password(TEST_PASSWORD),
            ),
        )
        account_id = cursor.lastrowid
        db.commit()

    return account_id


def test_session_2fa_identifiant_inexistant(client):
    with client.session_transaction() as session:
        session.update(
            pending_role="client",
            pending_id=999999,
            pending_session_version=0,
            pending_at=int(time.time()),
        )

    response = client.get("/auth/2fa")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/portail")


def test_session_2fa_role_invalide(client):
    with client.session_transaction() as session:
        session.update(
            pending_role="administrateur-invalide",
            pending_id=1,
            pending_session_version=0,
            pending_at=int(time.time()),
        )

    response = client.get("/auth/2fa")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/portail")


def test_page_2fa_sans_authentification(client):
    response = client.get("/auth/2fa")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/portail")


def test_connexion_client_valide_redirige_vers_2fa(
    client,
    test_account,
):
    with client.session_transaction() as session:
        session["csrf"] = CSRF

    response = client.post(
        "/portail",
        data={
            "csrf_token": CSRF,
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD,
        },
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/auth/2fa/configurer")

    with client.session_transaction() as session:
        assert session["pending_role"] == "client"
        assert session["pending_id"] == test_account
        assert session.get("role") is None


def test_configuration_2fa_genere_secret(client, test_account):
    from app import DB, reveal

    with client.session_transaction() as session:
        session["csrf"] = CSRF

    connexion = client.post(
        "/portail",
        data={
            "csrf_token": CSRF,
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD,
        },
    )

    assert connexion.status_code == 302

    response = client.get("/auth/2fa/configurer")

    assert response.status_code == 200

    with sqlite3.connect(DB) as db:
        row = db.execute(
            """
            SELECT secret_enc, enabled
            FROM totp_accounts
            WHERE account_role = ?
              AND account_id = ?
            """,
            ("client", test_account),
        ).fetchone()

    assert row is not None
    assert row[0] is not None
    assert row[1] == 0

    secret = reveal(row[0])

    assert isinstance(secret, str)
    assert len(secret) >= 16


def test_activation_2fa_avec_code_valide(client, test_account):
    from app import DB, reveal

    with client.session_transaction() as session:
        session["csrf"] = CSRF

    connexion = client.post(
        "/portail",
        data={
            "csrf_token": CSRF,
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD,
        },
    )

    assert connexion.status_code == 302

    configuration = client.get("/auth/2fa/configurer")
    assert configuration.status_code == 200

    with sqlite3.connect(DB) as db:
        row = db.execute(
            """
            SELECT secret_enc
            FROM totp_accounts
            WHERE account_role = ?
              AND account_id = ?
            """,
            ("client", test_account),
        ).fetchone()

    assert row is not None

    secret = reveal(row[0])
    code = pyotp.TOTP(secret).now()

    with client.session_transaction() as session:
        session["csrf"] = CSRF

    response = client.post(
        "/auth/2fa/configurer",
        data={
            "csrf_token": CSRF,
            "code": code,
        },
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/auth/2fa/recuperation")

    with sqlite3.connect(DB) as db:
        enabled = db.execute(
            """
            SELECT enabled
            FROM totp_accounts
            WHERE account_role = ?
              AND account_id = ?
            """,
            ("client", test_account),
        ).fetchone()[0]

    assert enabled == 1


def test_connexion_client_avec_2fa_activee(client, test_account):
    from app import DB, protect

    secret = pyotp.random_base32()

    with sqlite3.connect(DB) as db:
        db.execute(
            """
            INSERT INTO totp_accounts (
                account_role,
                account_id,
                secret_enc,
                enabled,
                last_counter
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                "client",
                test_account,
                protect(secret),
                1,
                -1,
            ),
        )
        db.commit()

    with client.session_transaction() as session:
        session["csrf"] = CSRF

    response = client.post(
        "/portail",
        data={
            "csrf_token": CSRF,
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD,
        },
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/auth/2fa")

    with client.session_transaction() as session:
        assert session["pending_role"] == "client"
        assert session["pending_id"] == test_account
        assert session.get("role") is None

    protected_response = client.get("/client")

    assert protected_response.status_code == 302
    assert protected_response.headers["Location"].endswith("/portail")


def test_connexion_2fa_valide_ouvre_espace_client(client, test_account):
    from app import DB, protect

    secret = pyotp.random_base32()

    with sqlite3.connect(DB) as db:
        db.execute(
            """
            INSERT INTO totp_accounts (
                account_role,
                account_id,
                secret_enc,
                enabled,
                last_counter
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            ("client", test_account, protect(secret), 1, -1),
        )
        db.commit()

    with client.session_transaction() as session:
        session["csrf"] = CSRF

    connexion = client.post(
        "/portail",
        data={
            "csrf_token": CSRF,
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD,
        },
    )

    assert connexion.status_code == 302
    assert connexion.headers["Location"].endswith("/auth/2fa")

    code = pyotp.TOTP(secret).now()

    with client.session_transaction() as session:
        session["csrf"] = CSRF

    validation = client.post(
        "/auth/2fa",
        data={
            "csrf_token": CSRF,
            "code": code,
        },
    )

    assert validation.status_code == 302
    assert validation.headers["Location"].endswith("/client")

    with client.session_transaction() as session:
        assert session["role"] == "client"
        assert session["user_id"] == test_account
        assert session.get("pending_role") is None

    espace_client = client.get("/client")

    assert espace_client.status_code == 200


def test_code_totp_deja_utilise_est_refuse(client, test_account):
    from app import DB, protect

    secret = pyotp.random_base32()
    code = pyotp.TOTP(secret).now()

    with sqlite3.connect(DB) as db:
        db.execute(
            """
            INSERT INTO totp_accounts (
                account_role,
                account_id,
                secret_enc,
                enabled,
                last_counter
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            ("client", test_account, protect(secret), 1, -1),
        )
        db.commit()

    def commencer_connexion():
        with client.session_transaction() as session:
            session.clear()
            session["csrf"] = CSRF

        response = client.post(
            "/portail",
            data={
                "csrf_token": CSRF,
                "email": TEST_EMAIL,
                "password": TEST_PASSWORD,
            },
        )

        assert response.status_code == 302
        assert response.headers["Location"].endswith("/auth/2fa")

    def valider_code(code_totp):
        # Restaurer un jeton CSRF valide pour la session courante.
        with client.session_transaction() as session:
            session["csrf"] = CSRF

        return client.post(
            "/auth/2fa",
            data={
                "csrf_token": CSRF,
                "code": code_totp,
            },
        )

    # Première connexion : le code TOTP doit être accepté.
    commencer_connexion()

    premiere_validation = valider_code(code)

    assert premiere_validation.status_code == 302
    assert premiere_validation.headers["Location"].endswith("/client")

    with client.session_transaction() as session:
        assert session["role"] == "client"
        assert session["user_id"] == test_account

    # Deuxième connexion avec le même compte.
    commencer_connexion()

    # Réutilisation du même code TOTP.
    seconde_validation = valider_code(code)

    assert not (
        seconde_validation.status_code == 302
        and seconde_validation.headers["Location"].endswith("/client")
    )

    # La seconde tentative ne doit pas authentifier le client.
    with client.session_transaction() as session:
        assert session.get("role") != "client"
        assert session.get("user_id") is None

    # L'espace client doit rester inaccessible.
    espace_client = client.get("/client")

    assert espace_client.status_code == 302
    assert espace_client.headers["Location"].endswith("/portail")


def test_deconnexion_invalide_session_client(client, test_account):
    from app import DB, protect

    secret = pyotp.random_base32()

    with sqlite3.connect(DB) as db:
        db.execute(
            """
            INSERT INTO totp_accounts (
                account_role,
                account_id,
                secret_enc,
                enabled,
                last_counter
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            ("client", test_account, protect(secret), 1, -1),
        )
        db.commit()

    # Première étape : connexion avec mot de passe.
    with client.session_transaction() as session:
        session["csrf"] = CSRF

    connexion = client.post(
        "/portail",
        data={
            "csrf_token": CSRF,
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD,
        },
    )

    assert connexion.status_code == 302
    assert connexion.headers["Location"].endswith("/auth/2fa")

    # Deuxième étape : validation TOTP.
    with client.session_transaction() as session:
        session["csrf"] = CSRF

    validation = client.post(
        "/auth/2fa",
        data={
            "csrf_token": CSRF,
            "code": pyotp.TOTP(secret).now(),
        },
    )

    assert validation.status_code == 302
    assert validation.headers["Location"].endswith("/client")

    # L'utilisateur est authentifié.
    assert client.get("/client").status_code == 200

    # Troisième étape : déconnexion par POST.
    with client.session_transaction() as session:
        session["csrf"] = CSRF

    deconnexion = client.post(
        "/deconnexion",
        data={"csrf_token": CSRF},
    )

    assert deconnexion.status_code == 302

    # La session ne doit plus contenir d'identité.
    with client.session_transaction() as session:
        assert session.get("role") is None
        assert session.get("user_id") is None
        assert session.get("pending_role") is None

    # L'espace client doit redevenir inaccessible.
    response = client.get("/client")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/portail")


def test_connexion_cabinet_redirige_vers_2fa(
    client,
    test_cabinet_account,
):
    with client.session_transaction() as session:
        session["csrf"] = CSRF

    response = client.post(
        "/cabinet/connexion",
        data={
            "csrf_token": CSRF,
            "email": "cabinet-test@datensis.fr",
            "password": TEST_PASSWORD,
        },
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/auth/2fa/configurer")

    with client.session_transaction() as session:
        assert session["pending_role"] == "cabinet"
        assert session["pending_id"] == test_cabinet_account
        assert session.get("role") is None
        assert session.get("admin_id") is None

    # L'espace cabinet reste inaccessible avant la 2FA.
    protected_response = client.get("/cabinet")

    assert protected_response.status_code == 302
    assert protected_response.headers["Location"].endswith("/cabinet/connexion")


def test_connexion_cabinet_2fa_valide(
    client,
    test_cabinet_account,
):
    from app import DB, protect

    secret = pyotp.random_base32()

    with sqlite3.connect(DB) as db:
        db.execute(
            """
            INSERT INTO totp_accounts (
                account_role,
                account_id,
                secret_enc,
                enabled,
                last_counter
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                "cabinet",
                test_cabinet_account,
                protect(secret),
                1,
                -1,
            ),
        )
        db.commit()

    # Connexion avec le mot de passe.
    with client.session_transaction() as session:
        session["csrf"] = CSRF

    connexion = client.post(
        "/cabinet/connexion",
        data={
            "csrf_token": CSRF,
            "email": "cabinet-test@datensis.fr",
            "password": TEST_PASSWORD,
        },
    )

    assert connexion.status_code == 302
    assert connexion.headers["Location"].endswith("/auth/2fa")

    # Validation du code TOTP.
    with client.session_transaction() as session:
        session["csrf"] = CSRF

    validation = client.post(
        "/auth/2fa",
        data={
            "csrf_token": CSRF,
            "code": pyotp.TOTP(secret).now(),
        },
    )

    assert validation.status_code == 302
    assert validation.headers["Location"].endswith("/cabinet")

    # Vérification de la session cabinet.
    with client.session_transaction() as session:
        assert session["role"] == "cabinet"
        assert session["admin_id"] == test_cabinet_account
        assert session.get("user_id") is None
        assert session.get("pending_role") is None

    # Accès autorisé à l'espace cabinet.
    assert client.get("/cabinet").status_code == 200

    # Accès interdit à l'espace client.
    espace_client = client.get("/client")

    assert espace_client.status_code == 302
    assert espace_client.headers["Location"].endswith("/portail")


def test_session_cabinet_invalidee_apres_changement_version(
    client, test_cabinet_account
):
    from app import DB

    with sqlite3.connect(DB) as db:
        row = db.execute(
            "SELECT session_version FROM cabinet_admins WHERE id = ?",
            (test_cabinet_account,),
        ).fetchone()
    assert row is not None

    with client.session_transaction() as session:
        session.clear()
        session.update(
            role="cabinet",
            admin_id=test_cabinet_account,
            session_version=row[0],
        )

    assert client.get("/cabinet").status_code == 200

    with sqlite3.connect(DB) as db:
        db.execute(
            "UPDATE cabinet_admins SET session_version = session_version + 1 WHERE id = ?",
            (test_cabinet_account,),
        )
        db.commit()

    response = client.get("/cabinet")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/cabinet/connexion")
    with client.session_transaction() as session:
        assert session.get("role") is None
        assert session.get("admin_id") is None
        assert session.get("session_version") is None


def test_session_client_invalidee_apres_changement_version(client, test_account):
    from app import DB

    with sqlite3.connect(DB) as db:
        row = db.execute(
            "SELECT session_version FROM users WHERE id = ?", (test_account,)
        ).fetchone()
    assert row is not None

    with client.session_transaction() as session:
        session.clear()
        session.update(role="client", user_id=test_account, session_version=row[0])

    assert client.get("/client").status_code == 200

    with sqlite3.connect(DB) as db:
        db.execute(
            "UPDATE users SET session_version = session_version + 1 WHERE id = ?",
            (test_account,),
        )
        db.commit()

    response = client.get("/client")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/portail")
    with client.session_transaction() as session:
        assert session.get("role") is None
        assert session.get("user_id") is None
        assert session.get("session_version") is None


def test_session_2fa_expiree(client, test_account):
    from app import DB

    with sqlite3.connect(DB) as db:
        version = db.execute(
            "SELECT session_version FROM users WHERE id = ?", (test_account,)
        ).fetchone()[0]

    with client.session_transaction() as session:
        session.clear()
        session.update(
            pending_role="client",
            pending_id=test_account,
            pending_session_version=version,
            pending_at=int(time.time()) - 86400,
        )

    response = client.get("/auth/2fa")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/portail")
    with client.session_transaction() as session:
        assert session.get("pending_role") is None
        assert session.get("pending_id") is None


def test_session_2fa_version_revoquee(client, test_account):
    from app import DB

    with sqlite3.connect(DB) as db:
        version = db.execute(
            "SELECT session_version FROM users WHERE id = ?", (test_account,)
        ).fetchone()[0]

    with client.session_transaction() as session:
        session.clear()
        session.update(
            pending_role="client",
            pending_id=test_account,
            pending_session_version=version,
            pending_at=int(time.time()),
        )

    with sqlite3.connect(DB) as db:
        db.execute(
            "UPDATE users SET session_version = session_version + 1 WHERE id = ?",
            (test_account,),
        )
        db.commit()

    response = client.get("/auth/2fa")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/portail")
    with client.session_transaction() as session:
        assert session.get("pending_role") is None


def test_code_totp_incorrect_refuse(client, test_account):
    from app import DB, protect

    secret = pyotp.random_base32()
    code_valide = pyotp.TOTP(secret).now()
    code_invalide = "000000" if code_valide != "000000" else "999999"

    with sqlite3.connect(DB) as db:
        db.execute(
            """
            INSERT INTO totp_accounts (
                account_role, account_id, secret_enc, enabled, last_counter
            ) VALUES (?, ?, ?, ?, ?)
            """,
            ("client", test_account, protect(secret), 1, -1),
        )
        db.commit()

    with client.session_transaction() as session:
        session["csrf"] = CSRF
    connexion = client.post(
        "/portail",
        data={"csrf_token": CSRF, "email": TEST_EMAIL, "password": TEST_PASSWORD},
    )
    assert connexion.status_code == 302
    assert connexion.headers["Location"].endswith("/auth/2fa")

    with client.session_transaction() as session:
        session["csrf"] = CSRF
    response = client.post(
        "/auth/2fa", data={"csrf_token": CSRF, "code": code_invalide}
    )
    assert not (
        response.status_code == 302 and response.headers["Location"].endswith("/client")
    )
    with client.session_transaction() as session:
        assert session.get("role") != "client"
        assert session.get("user_id") is None
    assert client.get("/client").status_code == 302


def test_session_client_ne_donne_pas_acces_cabinet(client, test_account):
    from app import DB

    with sqlite3.connect(DB) as db:
        version = db.execute(
            "SELECT session_version FROM users WHERE id = ?", (test_account,)
        ).fetchone()[0]

    with client.session_transaction() as session:
        session.clear()
        session.update(role="client", user_id=test_account, session_version=version)

    assert client.get("/client").status_code == 200
    response = client.get("/cabinet")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/cabinet/connexion")


def test_session_cabinet_ne_donne_pas_acces_client(client, test_cabinet_account):
    from app import DB

    with sqlite3.connect(DB) as db:
        version = db.execute(
            "SELECT session_version FROM cabinet_admins WHERE id = ?",
            (test_cabinet_account,),
        ).fetchone()[0]

    with client.session_transaction() as session:
        session.clear()
        session.update(
            role="cabinet", admin_id=test_cabinet_account, session_version=version
        )

    assert client.get("/cabinet").status_code == 200
    response = client.get("/client")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/portail")
