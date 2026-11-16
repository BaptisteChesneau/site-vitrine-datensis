import pytest


@pytest.mark.parametrize(
    "route",
    [
        "/portail",
        "/inscription",
        "/cabinet/connexion",
        "/mot-de-passe-oublie",
        "/deconnexion",
    ],
)
def test_post_sans_csrf_refuse(client, route):
    response = client.post(route, data={})

    assert response.status_code == 400


def test_post_avec_csrf_invalide_refuse(client):
    with client.session_transaction() as session:
        session["csrf"] = "jeton-valide-de-test"

    response = client.post(
        "/portail",
        data={
            "csrf_token": "jeton-invalide",
            "email": "test@example.com",
            "password": "MotDePasse123!",
        },
    )

    assert response.status_code == 400


def test_post_avec_csrf_valide(client):
    with client.session_transaction() as session:
        session["csrf"] = "jeton-valide-de-test"

    response = client.post(
        "/portail",
        data={
            "csrf_token": "jeton-valide-de-test",
            "email": "inconnu@example.com",
            "password": "MotDePasse123!",
        },
    )

    # La requête passe la validation CSRF.
    # L'authentification reste refusée.
    assert response.status_code == 200


@pytest.mark.parametrize(
    ("email", "expected"),
    [
        ("client@example.com", True),
        ("cabinet@datensis.fr", True),
        ("prenom.nom@example.fr", True),
        ("adresse-invalide", False),
        ("sans-arobase.fr", False),
        ("client@", False),
        ("@example.com", False),
        ("client@example", False),
        ("client @example.com", False),
    ],
)
def test_validation_email(email, expected):
    from app import email_valid

    assert email_valid(email) is expected
