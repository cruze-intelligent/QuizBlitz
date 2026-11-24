"""Application configuration for the QuizBlitz project.

The active configuration is chosen by QUIZBLITZ_ENV ("development" or "production").
wsgi.py (the production entry point) defaults to production; everything else to development.
"""

import os
import secrets
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


def local_secret_key() -> str:
    """A random key for this machine, created once and kept in instance/ (gitignored).

    Used only outside production, so a local server never signs cookies with a value that
    is published in the source code.
    """
    path = Path(BASE_DIR) / "instance" / "dev_secret_key"
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    path.parent.mkdir(exist_ok=True)
    key = secrets.token_hex(32)
    path.write_text(key, encoding="utf-8")
    return key


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY")
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL") or f"sqlite:///{os.path.join(BASE_DIR, 'quizblitz.db')}"
    # Each phone holds one server thread, and events run in their own threads, so allow a
    # burst of short-lived connections when a whole room answers at once.
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_size": 10, "max_overflow": 40}
    LOG_DIR = os.environ.get("QUIZBLITZ_LOG_DIR") or os.path.join(BASE_DIR, "logs")

    # CSRF tokens last as long as the login. The default (1 hour) would reject "Start quiz"
    # if the lobby had been open on the projector for longer than that.
    WTF_CSRF_TIME_LIMIT = None

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"
    # Team cookies are permanent so a phone that closes its browser mid-game keeps its team.
    PERMANENT_SESSION_LIFETIME = timedelta(hours=12)

    MAX_CONTENT_LENGTH = 1024 * 1024
    # In-memory counters are correct because the app always runs as a single process.
    RATELIMIT_STORAGE_URI = "memory://"

    MAX_TEAMS_PER_SESSION = 150
    BEHIND_PROXY = False


class DevelopmentConfig(Config):
    pass


class ProductionConfig(Config):
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True
    PREFERRED_URL_SCHEME = "https"
    BEHIND_PROXY = True  # Caddy terminates HTTPS and forwards the real host/scheme/IP
    LOG_DIR = os.environ.get("QUIZBLITZ_LOG_DIR")  # unset: log to stderr (journald)


class TestingConfig(Config):
    TESTING = True
    SECRET_KEY = "test-only-key"
    WTF_CSRF_ENABLED = False
    RATELIMIT_ENABLED = False
    LOG_DIR = None


config = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
}
