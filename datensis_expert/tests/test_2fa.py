import pyotp
import pytest


@pytest.fixture
def totp_secret():
    return pyotp.random_base32()


def test_code_totp_valide(app, totp_secret):
    from app import otp_valid

    code = pyotp.TOTP(totp_secret).now()

    assert otp_valid(totp_secret, code) is True


def test_code_totp_incorrect(app, totp_secret):
    from app import otp_valid

    totp = pyotp.TOTP(totp_secret)
    code = totp.now()

    # Un code différent du code actuel.
    incorrect = str((int(code) + 1) % 1_000_000).zfill(6)

    assert otp_valid(totp_secret, incorrect) is False


@pytest.mark.parametrize(
    "code",
    [
        "",
        "123",
        "abcdef",
        "1234567",
        "12 456",
        "123-56",
    ],
)
def test_format_code_totp_invalide(app, totp_secret, code):
    from app import otp_valid

    assert otp_valid(totp_secret, code) is False


def test_compteur_totp_valide(app, totp_secret):
    from app import otp_counter

    code = pyotp.TOTP(totp_secret).now()

    assert otp_counter(totp_secret, code) is not None


def test_compteur_totp_format_invalide(app, totp_secret):
    from app import otp_counter

    assert otp_counter(totp_secret, "code-invalide") is None


def test_page_2fa_sans_session(client):
    response = client.get("/auth/2fa")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/portail")


def test_configuration_2fa_sans_session(client):
    response = client.get("/auth/2fa/configurer")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/portail")


def test_recuperation_2fa_sans_session(client):
    response = client.get("/auth/2fa/recuperation")

    assert response.status_code == 404
