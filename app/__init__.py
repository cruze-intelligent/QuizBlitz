"""Flask application factory for QuizBlitz."""

import logging
import os
import sqlite3
from logging.handlers import RotatingFileHandler
from pathlib import Path

from flask import Flask, jsonify, redirect, render_template
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_socketio import SocketIO
from flask_wtf.csrf import CSRFError, CSRFProtect
from sqlalchemy import event, text
from sqlalchemy.engine import Engine
from werkzeug.middleware.proxy_fix import ProxyFix

from app.models import QuizMaster, User, db
from config import config, local_secret_key

MIGRATIONS_DIR = str(Path(__file__).resolve().parent.parent / "migrations")

# Plain threads: works with Werkzeug locally and Gunicorn's gthread worker in production.
# No cors_allowed_origins: browsers may only connect from the site itself.
socketio = SocketIO(async_mode="threading", max_http_buffer_size=100_000)

login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message = "Please log in to access this page."
login_manager.login_message_category = "warning"

csrf = CSRFProtect()
limiter = Limiter(key_func=get_remote_address)
migrate = Migrate()


@login_manager.user_loader
def load_user(user_id: str):
    """Load a User or QuizMaster from a prefixed id ("user:1" / "master:1").

    Both tables number from 1, so a bare numeric id is ambiguous. Old-style
    bare ids are rejected, which simply forces a fresh login.
    """
    kind, _, raw_id = (user_id or "").partition(":")
    model = {"user": User, "master": QuizMaster}.get(kind)
    if model is None or not raw_id.isdigit():
        return None
    return db.session.get(model, int(raw_id))


@event.listens_for(Engine, "connect")
def _configure_sqlite(dbapi_connection, _record):
    """WAL lets phones read while an answer is being written; busy_timeout queues writers."""
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=10000")
        cursor.close()


def create_app(config_name: str | None = None, **overrides) -> Flask:
    config_name = config_name or os.environ.get("QUIZBLITZ_ENV") or "development"
    if config_name not in config:
        raise RuntimeError(f"Unknown QUIZBLITZ_ENV {config_name!r}; use one of: {', '.join(config)}.")

    app = Flask(__name__)
    app.config.from_object(config[config_name])
    app.config.update(overrides)
    _check_secret_key(app, config_name)
    _configure_logging(app)

    db.init_app(app)
    migrate.init_app(app, db, directory=MIGRATIONS_DIR)
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)
    # Handlers must be registered before init_app: that way every app instance gets them.
    from app.sockets import events  # noqa: F401

    socketio.init_app(app)

    from app.admin.routes import admin_bp
    from app.auth.routes import auth_bp
    from app.cli import register_commands
    from app.master.routes import master_bp
    from app.play.routes import play_bp
    from app.quiz.routes import quiz_bp

    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(master_bp, url_prefix="/master")
    app.register_blueprint(play_bp, url_prefix="/play")
    app.register_blueprint(quiz_bp, url_prefix="/quiz")
    app.register_blueprint(admin_bp, url_prefix="/admin")

    @app.route("/")
    def index():
        from app.auth.routes import home_url

        return redirect(home_url())

    @app.route("/health")
    @limiter.exempt
    def health():
        try:
            db.session.execute(text("SELECT 1"))
        except Exception:
            return jsonify({"status": "degraded", "database": "unavailable"}), 503
        return jsonify({"status": "ok", "database": "connected"})

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        return response

    _register_error_pages(app)
    _register_filters(app)
    register_commands(app)

    if app.config["BEHIND_PROXY"]:
        # Trust exactly one proxy hop, so QR links use https://<public host> and rate
        # limits see each visitor's address. The app must only be reachable via the proxy.
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    app.logger.info("QuizBlitz started with %s configuration", config_name)
    return app


def _check_secret_key(app: Flask, config_name: str) -> None:
    """Anyone who knows SECRET_KEY can forge an admin login, so production must supply one."""
    key = app.config["SECRET_KEY"]
    if config_name == "production":
        if not key or len(key) < 32 or key.startswith(("dev-", "change", "replace")):
            raise RuntimeError(
                "Production needs a private SECRET_KEY of at least 32 characters. Generate one with:\n"
                '  python -c "import secrets; print(secrets.token_hex(32))"'
            )
    elif not key:
        app.config["SECRET_KEY"] = local_secret_key()


def _configure_logging(app: Flask) -> None:
    app.logger.setLevel(logging.INFO)
    if app.config["LOG_DIR"]:
        log_dir = Path(app.config["LOG_DIR"])
        log_dir.mkdir(parents=True, exist_ok=True)
        if not any(isinstance(handler, RotatingFileHandler) for handler in app.logger.handlers):
            handler = RotatingFileHandler(
                log_dir / "quizblitz.log", maxBytes=1_048_576, backupCount=5, encoding="utf-8"
            )
            handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
            app.logger.addHandler(handler)
    app.logger.propagate = False


def _register_error_pages(app: Flask) -> None:
    def page(status: int, title: str, message: str):
        return render_template("error.html", title=title, message=message), status

    @app.errorhandler(403)
    def forbidden(_error):
        return page(403, "Not allowed", "Your account doesn't have access to this page.")

    @app.errorhandler(404)
    def not_found(_error):
        return page(404, "Page not found", "Check the link, or scan the QR code again.")

    @app.errorhandler(429)
    def too_many_requests(_error):
        return page(429, "Too many attempts", "Please wait a few minutes, then try again.")

    @app.errorhandler(CSRFError)
    def csrf_failed(_error):
        return page(400, "This page has expired", "Go back, refresh the page and try again.")


def _register_filters(app: Flask) -> None:
    """Register small Jinja2 filters used by the templates."""

    _AVATAR_HUES = [270, 200, 145, 35, 320, 175, 55, 230, 10, 290]

    @app.template_filter("avatar_color")
    def avatar_color(index: int) -> str:
        hue = _AVATAR_HUES[(int(index) - 1) % len(_AVATAR_HUES)]
        return f"hsl({hue}, 65%, 45%)"
