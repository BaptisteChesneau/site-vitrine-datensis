def test_accueil_redirige_vers_portail(client):
    response = client.get("/")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/portail")


def test_page_connexion_client(client):
    response = client.get("/portail")

    assert response.status_code == 200


def test_page_inscription(client):
    response = client.get("/inscription")

    assert response.status_code == 200


def test_page_connexion_cabinet(client):
    response = client.get("/cabinet/connexion")

    assert response.status_code == 200


def test_espace_client_protege(client):
    response = client.get("/client")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/portail")


def test_espace_cabinet_protege(client):
    response = client.get("/cabinet")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/cabinet/connexion")


def test_deconnexion_refuse_get(client):
    response = client.get("/deconnexion")

    assert response.status_code == 405


def test_entetes_securite(client):
    response = client.get("/portail")

    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "Content-Security-Policy" in response.headers
