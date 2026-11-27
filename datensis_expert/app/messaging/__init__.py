"""Module de messagerie DATENSIS Expert."""

from importlib import import_module

from flask import Blueprint

messaging_bp = Blueprint(
    "messaging",
    __name__,
    url_prefix="/api",
)

import_module(".routes", package=__name__)
