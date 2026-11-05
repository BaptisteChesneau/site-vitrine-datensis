import os

from dotenv import load_dotenv
from flask import Flask

from app.extensions import csrf, db


def create_app(test_config=None):
    load_dotenv()
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=os.getenv("SECRET_KEY", "development-only-change-this-key"),
        SQLALCHEMY_DATABASE_URI=os.getenv("DATABASE_URL", "sqlite:///datensis.db"),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        MAX_CONTENT_LENGTH=1024 * 1024,
    )
    if test_config:
        app.config.update(test_config)
    if not app.debug and not app.testing and app.config["SECRET_KEY"] == "development-only-change-this-key":
        raise RuntimeError("Configurez SECRET_KEY avant la production.")

    db.init_app(app)
    csrf.init_app(app)

    from app.routes.main import main

    app.register_blueprint(main)
    return app
