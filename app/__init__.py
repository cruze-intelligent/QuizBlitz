"""Flask application factory for QuizBlitz."""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

import click
from flask import Flask, jsonify, redirect, url_for
from flask_login import LoginManager
from flask_socketio import SocketIO
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import text

from config import config
from app.models import (
    db,
    GameSession,
    Option,
    Question,
    Quiz,
    QuizMaster,
    Team,
    TeamAnswer,
    User,
)


socketio = SocketIO(async_mode="eventlet", cors_allowed_origins="*")

login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message = "Please log in to access this page."
login_manager.login_message_category = "warning"

csrf = CSRFProtect()


@login_manager.user_loader
def load_user(user_id: str):
    """Load any supported user type from the session."""
    for model in (User, QuizMaster):
        user = db.session.get(model, int(user_id))
        if user is not None:
            return user
    return None


def create_app(config_name: str = "default") -> Flask:
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    log_dir = Path(__file__).resolve().parent.parent / "logs"
    log_dir.mkdir(exist_ok=True)
    if not any(isinstance(handler, RotatingFileHandler) for handler in app.logger.handlers):
        file_handler = RotatingFileHandler(log_dir / "quizblitz.log", maxBytes=1_048_576, backupCount=5, encoding="utf-8")
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        app.logger.addHandler(file_handler)
    app.logger.setLevel(logging.INFO)
    app.logger.propagate = False

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    socketio.init_app(app)

    from app.admin.routes import admin_bp
    from app.auth.routes import auth_bp
    from app.master.routes import master_bp
    from app.play.routes import play_bp
    from app.quiz.routes import quiz_bp
    from app.sockets import events  # noqa: F401

    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(master_bp, url_prefix="/master")
    app.register_blueprint(play_bp, url_prefix="/play")
    app.register_blueprint(quiz_bp, url_prefix="/quiz")
    app.register_blueprint(admin_bp, url_prefix="/admin")

    @app.route("/")
    def index():
        return redirect(url_for("master.dashboard"))

    @app.route("/health")
    def health():
        try:
            db.session.execute(text("SELECT 1"))
            status = "ok"
            db_state = "connected"
        except Exception:
            status = "degraded"
            db_state = "unavailable"
        return jsonify({"status": status, "database": db_state})

    _register_filters(app)
    _register_commands(app)

    with app.app_context():
        db.create_all()

    app.logger.info("QuizBlitz started with %s configuration", config_name)
    return app


def _register_filters(app: Flask) -> None:
    """Register small Jinja2 filters used by the templates."""

    _AVATAR_HUES = [270, 200, 145, 35, 320, 175, 55, 230, 10, 290]

    @app.template_filter("avatar_color")
    def avatar_color(index: int) -> str:
        hue = _AVATAR_HUES[(int(index) - 1) % len(_AVATAR_HUES)]
        return f"hsl({hue}, 65%, 45%)"


def _register_commands(app: Flask) -> None:
    """Attach CLI commands for local development and data seeding."""

    @app.cli.command("seed-db")
    def seed_db():
        """Seed quiz master and sample quiz data for the live game."""
        click.echo("[*] Seeding database ...")

        db.session.query(TeamAnswer).delete()
        db.session.query(Team).delete()
        db.session.query(GameSession).delete()
        db.session.query(Option).delete()
        db.session.query(Question).delete()
        db.session.query(Quiz).delete()
        db.session.query(QuizMaster).delete()
        db.session.query(User).delete()
        db.session.commit()

        master = QuizMaster(username="master", email="master@quizblitz.com")
        master.set_password("master123")
        db.session.add(master)
        db.session.flush()

        admin = User(username="admin", email="admin@quizblitz.com", is_admin=True)
        admin.set_password("admin123")
        db.session.add(admin)
        db.session.flush()

        quiz = Quiz(
            title="General Knowledge",
            description="A lively general knowledge challenge.",
            category="General",
            difficulty="easy",
            time_limit_seconds=30,
            is_published=True,
            created_by=master.id,
        )
        db.session.add(quiz)
        db.session.flush()

        rounds = [
            ("Science", [
                {"text": "Which planet is known as the Red Planet?", "options": ["Venus", "Mars", "Jupiter", "Saturn"], "correct": 1},
                {"text": "What gas do plants absorb from the atmosphere?", "options": ["Oxygen", "Nitrogen", "Carbon dioxide", "Helium"], "correct": 2},
                {"text": "Which organ pumps blood around the body?", "options": ["Lungs", "Heart", "Liver", "Kidney"], "correct": 1},
                {"text": "Which element has the chemical symbol O?", "options": ["Gold", "Oxygen", "Osmium", "Argon"], "correct": 1},
                {"text": "What is the freezing point of water in Celsius?", "options": ["0", "10", "-10", "100"], "correct": 0},
            ]),
            ("History", [
                {"text": "Who was the first President of the United States?", "options": ["Benjamin Franklin", "Thomas Jefferson", "George Washington", "John Adams"], "correct": 2},
                {"text": "Which ancient civilization built Machu Picchu?", "options": ["Romans", "Maya", "Inca", "Greeks"], "correct": 2},
                {"text": "The Great Fire of London happened in which year?", "options": ["1663", "1665", "1666", "1668"], "correct": 2},
                {"text": "Who discovered penicillin?", "options": ["Marie Curie", "Alexander Fleming", "Isaac Newton", "Albert Einstein"], "correct": 1},
                {"text": "Which empire built the Colosseum?", "options": ["Roman Empire", "Ottoman Empire", "Mongol Empire", "British Empire"], "correct": 0},
            ]),
            ("Sports", [
                {"text": "How many players are on a standard soccer team on the field?", "options": ["9", "10", "11", "12"], "correct": 2},
                {"text": "In tennis, what is the term for a score of zero?", "options": ["Love", "Draw", "Nil", "Blank"], "correct": 0},
                {"text": "Which country hosted the 2016 Summer Olympics?", "options": ["China", "Brazil", "Japan", "Greece"], "correct": 1},
                {"text": "Which sport uses the terms 'love', 'deuce', and 'advantage'?", "options": ["Cricket", "Tennis", "Golf", "Basketball"], "correct": 1},
                {"text": "How many points is a touchdown worth in American football?", "options": ["3", "6", "7", "8"], "correct": 1},
            ]),
        ]

        order_index = 0
        for round_number, (round_name, questions) in enumerate(rounds, start=1):
            for question_index, question_data in enumerate(questions, start=1):
                question = Question(
                    quiz_id=quiz.id,
                    text=question_data["text"],
                    round_number=round_number,
                    order_in_round=question_index,
                    order_index=order_index,
                    time_limit_seconds=30,
                    points=10,
                )
                db.session.add(question)
                db.session.flush()

                for option_index, option_text in enumerate(question_data["options"]):
                    db.session.add(
                        Option(
                            question_id=question.id,
                            text=option_text,
                            is_correct=(option_index == question_data["correct"]),
                            order_index=option_index,
                        )
                    )

                order_index += 1

        db.session.commit()
        click.echo("[OK] Database seeded successfully!")
        click.echo("   master@quizblitz.com / master123")
        click.echo("   admin@quizblitz.com / admin123")
