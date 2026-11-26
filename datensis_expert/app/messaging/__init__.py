"""Module de messagerie DATENSIS Expert."""

from flask import Blueprint
from . import routes  # noqa: E402, F401

messaging_bp = Blueprint(
    "messaging",
    __name__,
    url_prefix="/api",
)
