import pytest


@pytest.mark.parametrize(
    ("route", "status"),
    [
        ("/portail", 200),
        ("/cabinet/connexion", 401),
    ],
)
def test_identifiants_incorrects(client, route, status):
    with client.session_transaction() as session:
        session["csrf"] = "csrf-test-auth"

    response = client.post(
        route,
        data={
            "csrf_token": "csrf-test-auth",
            "email": "inconnu@example.com",
            "password": "MotDePasseIncorrect123!",
        },
    )

    assert response.status_code == status

    with client.session_transaction() as session:
        assert session.get("role") is None
        assert session.get("user_id") is None
        assert session.get("admin_id") is None


@pytest.mark.parametrize(
    ("route", "status"),
    [
        ("/portail", 200),
        ("/cabinet/connexion", 401),
    ],
)
def test_verrouillage_apres_cinq_echecs(client, route, status):
    with client.session_transaction() as session:
        session["csrf"] = "csrf-test-verrouillage"

    data = {
        "csrf_token": "csrf-test-verrouillage",
        "email": "verrouillage@example.com",
        "password": "MotDePasseIncorrect123!",
    }

    for _ in range(4):
        response = client.post(route, data=data)
        assert response.status_code == status

    # Le cinquième échec déclenche le verrouillage.
    response = client.post(route, data=data)
    assert response.status_code == status

    # La tentative suivante doit être bloquée.
    response = client.post(route, data=data)
    assert response.status_code == 429


def test_client_ne_peut_pas_acceder_au_cabinet(client):
    with client.session_transaction() as session:
        session["role"] = "client"
        session["user_id"] = 1
        session["session_version"] = 0

    response = client.get("/cabinet")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/cabinet/connexion")


def test_cabinet_ne_peut_pas_acceder_au_client(client):
    with client.session_transaction() as session:
        session["role"] = "cabinet"
        session["admin_id"] = 1
        session["session_version"] = 0

    response = client.get("/client")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/portail")
