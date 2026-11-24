"""Production entry point (see DEPLOY.md). Uses the production configuration by default.

    gunicorn --worker-class gthread --workers 1 --threads 200 --bind 127.0.0.1:8000 wsgi:app

Exactly one worker: live rooms and rate limits are kept in that process's memory. Every
connected phone holds one thread, so --threads caps how many can play at once.
"""

import os

# config.py loads .env when imported, so import the app before reading the environment.
from app import create_app

app = create_app(os.environ.get("QUIZBLITZ_ENV") or "production")
