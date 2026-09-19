import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask
from flask_wtf.csrf import CSRFProtect

from .db import init_app, init_db


def create_app(test_config=None):
    load_dotenv()
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY=os.getenv("SECRET_KEY", "development-secret"),
        DATABASE_PATH=os.getenv(
            "DATABASE_PATH",
            str(Path(app.instance_path) / "2gc_converter.sqlite3"),
        ),
        OPENROUTER_API_KEY=os.getenv("OPENROUTER_API_KEY", ""),
        OPENROUTER_MODEL=os.getenv(
            "OPENROUTER_MODEL", "nex-agi/nex-n2.5-mini:free"
        ),
        DEBUG=os.getenv("DEBUG", "false").lower() == "true",
        WTF_CSRF_ENABLED=True,
    )
    if test_config:
        app.config.update(test_config)

    csrf = CSRFProtect(app)
    if app.config.get("TESTING"):
        app.config["WTF_CSRF_ENABLED"] = False
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    init_app(app)
    with app.app_context():
        init_db()

    from .routes import main
    app.register_blueprint(main)
    return app
