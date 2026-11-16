import importlib

import pytest
from cryptography.fernet import Fernet


@pytest.fixture
def app(tmp_path, monkeypatch):
    # Configuration fictive réservée aux tests.
    monkeypatch.setenv("SECRET_KEY", "datensis-test-secret-key-32-caracteres-minimum")
    monkeypatch.setenv("DATENSIS_DATA_KEY", Fernet.generate_key().decode("ascii"))
    monkeypatch.setenv(
        "DATENSIS_INDEX_KEY", "datensis-test-index-key-32-caracteres-minimum"
    )
    monkeypatch.setenv("DATENSIS_ENV", "development")

    # Charger le module sans initialiser la vraie base.
    application = importlib.import_module("app")

    # Isoler la base SQLite pour chaque test.
    test_database = tmp_path / "expert_test.sqlite3"
    monkeypatch.setattr(application, "DB", test_database)

    # Isoler également les clés de chiffrement.
    application.CIPHER, application.INDEX_KEY = application._security_keys()

    flask_app = application.create_app()
    flask_app.config.update(TESTING=True)

    yield flask_app


@pytest.fixture
def client(app):
    return app.test_client()
