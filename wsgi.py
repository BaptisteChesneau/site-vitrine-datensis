"""Point d'entrée WSGI principal de DATENSIS."""

from werkzeug.middleware.dispatcher import DispatcherMiddleware

from site_vitrine_datensis.app import create_app as create_vitrine
from datensis_expert.app import create_app as create_expert


def create_application():
    """Initialise les deux applications Flask."""

    vitrine = create_vitrine()
    expert = create_expert()

    return DispatcherMiddleware(
        vitrine,
        {
            "/expert": expert,
        },
    )


# Application utilisée par Gunicorn sur Render
application = create_application()

# Alias WSGI
app = application
