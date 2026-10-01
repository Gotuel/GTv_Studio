import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask
from flask_wtf.csrf import CSRFProtect
from werkzeug.middleware.proxy_fix import ProxyFix

from .db import init_app, init_db


def create_app(test_config=None):
    load_dotenv()
    app = Flask(__name__, instance_relative_config=True)
    app_environment = os.getenv("APP_ENV", "development").lower()
    secret_key = os.getenv("SECRET_KEY")
    access_password = os.getenv("APP_ACCESS_PASSWORD", "")
    if app_environment == "production" and not secret_key:
        raise RuntimeError("SECRET_KEY doit être définie en production.")
    if app_environment == "production" and not access_password:
        raise RuntimeError("APP_ACCESS_PASSWORD doit être définie en production.")

    app.config.from_mapping(
        SECRET_KEY=secret_key or "development-only-secret",
        APP_ENV=app_environment,
        APP_ACCESS_PASSWORD=access_password,
        DATABASE_PATH=os.getenv(
            "DATABASE_PATH",
            str(Path(app.instance_path) / "2gc_converter.sqlite3"),
        ),
        DATABASE_URL=os.getenv("DATABASE_URL", ""),
        AUDIO_STORAGE_PATH=os.getenv(
            "AUDIO_STORAGE_PATH",
            str(Path(app.instance_path) / "audio"),
        ),
        STORAGE_BACKEND=os.getenv("STORAGE_BACKEND", "local").lower(),
        SUPABASE_URL=os.getenv("SUPABASE_URL", ""),
        SUPABASE_SERVICE_ROLE_KEY=os.getenv("SUPABASE_SERVICE_ROLE_KEY", ""),
        SUPABASE_STORAGE_BUCKET=os.getenv("SUPABASE_STORAGE_BUCKET", "gtv-audios"),
        OPENROUTER_API_KEY=os.getenv("OPENROUTER_API_KEY", ""),
        OPENROUTER_MODEL=os.getenv(
            "OPENROUTER_MODEL", "nex-agi/nex-n2.5-mini:free"
        ),
        DEBUG=os.getenv("DEBUG", "false").lower() == "true",
        MAX_CONTENT_LENGTH=2 * 1024 * 1024,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=app_environment == "production",
        WTF_CSRF_ENABLED=True,
    )
    if test_config:
        app.config.update(test_config)
    if app.config["STORAGE_BACKEND"] == "supabase" and not (
        app.config["SUPABASE_URL"] and app.config["SUPABASE_SERVICE_ROLE_KEY"]
    ):
        raise RuntimeError(
            "SUPABASE_URL et SUPABASE_SERVICE_ROLE_KEY sont requis pour le stockage Supabase."
        )
    if app.config["APP_ENV"] == "production" and not app.config["DATABASE_URL"]:
        raise RuntimeError("DATABASE_URL doit être définie en production.")

    CSRFProtect(app)
    if app_environment == "production":
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
    if app.config.get("TESTING"):
        app.config["WTF_CSRF_ENABLED"] = False
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    init_app(app)
    with app.app_context():
        init_db()

    from .routes import main
    app.register_blueprint(main)
    return app
