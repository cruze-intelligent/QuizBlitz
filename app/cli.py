"""Command-line tools: database setup, accounts and demo data.

    flask init-db         create or upgrade the database (safe to run repeatedly)
    flask create-master   add a quiz master (hosts live games)
    flask create-admin    add a site admin
    flask set-password    reset the password for an existing account
    flask seed-db         demo data for local development only
"""

import os
import secrets

import click
from flask import Flask
from sqlalchemy import inspect

from app.models import Option, Question, Quiz, QuizMaster, User, db, find_account

MIN_PASSWORD_LENGTH = 10
BASELINE_REVISION = "0001"


def upgrade_database(app: Flask) -> None:
    """Create the database or bring it up to date, keeping existing data."""
    from flask_migrate import stamp, upgrade

    with app.app_context():
        tables = set(inspect(db.engine).get_table_names())
        if "quizzes" in tables and "alembic_version" not in tables:
            # Created before migrations existed, by db.create_all(): that is the baseline.
            stamp(revision=BASELINE_REVISION)
        upgrade()


def _check_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise click.ClickException(f"Use a password of at least {MIN_PASSWORD_LENGTH} characters.")


def _create_account(model, username: str, email: str, password: str, **fields) -> None:
    username, email = username.strip(), email.strip().lower()
    _check_password(password)
    if not username or "@" not in email:
        raise click.ClickException("A username and a valid email address are required.")
    if find_account(email):
        raise click.ClickException(f"An account already uses {email}.")
    if model.query.filter_by(username=username).first():
        raise click.ClickException(f"The username {username} is already taken.")
    account = model(username=username, email=email, **fields)
    account.set_password(password)
    db.session.add(account)
    db.session.commit()


def register_commands(app: Flask) -> None:
    password_option = click.option("--password", prompt=True, hide_input=True, confirmation_prompt=True)

    @app.cli.command("init-db")
    def init_db():
        """Create or upgrade the database."""
        upgrade_database(app)
        click.echo("[OK] Database is up to date.")

    @app.cli.command("create-master")
    @click.option("--username", prompt=True)
    @click.option("--email", prompt=True)
    @password_option
    def create_master(username, email, password):
        """Add a quiz master account."""
        _create_account(QuizMaster, username, email, password)
        click.echo(f"[OK] Quiz master {username} created.")

    @app.cli.command("create-admin")
    @click.option("--username", prompt=True)
    @click.option("--email", prompt=True)
    @password_option
    def create_admin(username, email, password):
        """Add a site admin account."""
        _create_account(User, username, email, password, is_admin=True)
        click.echo(f"[OK] Admin {username} created.")

    @app.cli.command("set-password")
    @click.argument("email")
    @password_option
    def set_password(email, password):
        """Reset the password for an existing account."""
        account = find_account(email.strip().lower())
        if account is None:
            raise click.ClickException(f"No account uses {email}.")
        _check_password(password)
        account.set_password(password)
        db.session.commit()
        click.echo(f"[OK] Password changed for {account.email}.")

    @app.cli.command("seed-db")
    def seed_db():
        """Add demo accounts and a sample quiz to an empty local database."""
        if os.environ.get("QUIZBLITZ_ENV") == "production" or app.config["BEHIND_PROXY"]:
            raise click.ClickException("seed-db is for local development only. Use create-master instead.")
        if User.query.first() or QuizMaster.query.first() or Quiz.query.first():
            raise click.ClickException("The database already has data; seed-db never overwrites it.")

        master_password, admin_password = secrets.token_urlsafe(9), secrets.token_urlsafe(9)
        _create_account(QuizMaster, "master", "master@quizblitz.com", master_password)
        _create_account(User, "admin", "admin@quizblitz.com", admin_password, is_admin=True)
        _add_sample_quiz(QuizMaster.query.filter_by(username="master").one())

        click.echo("[OK] Database seeded. These passwords are shown only once:")
        click.echo(f"   master@quizblitz.com / {master_password}")
        click.echo(f"   admin@quizblitz.com / {admin_password}")


# (question, options, index of the correct option)
_SAMPLE_ROUNDS = [
    # Science
    [
        ("Which planet is known as the Red Planet?", ["Venus", "Mars", "Jupiter", "Saturn"], 1),
        ("What gas do plants absorb from the atmosphere?", ["Oxygen", "Nitrogen", "Carbon dioxide", "Helium"], 2),
        ("Which organ pumps blood around the body?", ["Lungs", "Heart", "Liver", "Kidney"], 1),
        ("Which element has the chemical symbol O?", ["Gold", "Oxygen", "Osmium", "Argon"], 1),
        ("What is the freezing point of water in Celsius?", ["0", "10", "-10", "100"], 0),
    ],
    # History
    [
        (
            "Who was the first President of the United States?",
            ["Benjamin Franklin", "Thomas Jefferson", "George Washington", "John Adams"],
            2,
        ),
        ("Which ancient civilization built Machu Picchu?", ["Romans", "Maya", "Inca", "Greeks"], 2),
        ("The Great Fire of London happened in which year?", ["1663", "1665", "1666", "1668"], 2),
        (
            "Who discovered penicillin?",
            ["Marie Curie", "Alexander Fleming", "Isaac Newton", "Albert Einstein"],
            1,
        ),
        (
            "Which empire built the Colosseum?",
            ["Roman Empire", "Ottoman Empire", "Mongol Empire", "British Empire"],
            0,
        ),
    ],
    # Sports
    [
        ("How many players are on a standard soccer team on the field?", ["9", "10", "11", "12"], 2),
        ("In tennis, what is the term for a score of zero?", ["Love", "Draw", "Nil", "Blank"], 0),
        ("Which country hosted the 2016 Summer Olympics?", ["China", "Brazil", "Japan", "Greece"], 1),
        (
            "Which sport uses the terms 'love', 'deuce', and 'advantage'?",
            ["Cricket", "Tennis", "Golf", "Basketball"],
            1,
        ),
        ("How many points is a touchdown worth in American football?", ["3", "6", "7", "8"], 1),
    ],
]


def _add_sample_quiz(master: QuizMaster) -> None:
    quiz = Quiz(
        title="General Knowledge",
        description="A lively general knowledge challenge.",
        category="General",
        difficulty="easy",
        time_limit_seconds=450,
        is_published=False,
        created_by=master.id,
    )
    db.session.add(quiz)
    db.session.flush()

    order_index = 0
    for round_number, questions in enumerate(_SAMPLE_ROUNDS, start=1):
        for order_in_round, (question_text, options, correct) in enumerate(questions, start=1):
            question = Question(
                quiz_id=quiz.id,
                text=question_text,
                round_number=round_number,
                order_in_round=order_in_round,
                order_index=order_index,
            )
            db.session.add(question)
            db.session.flush()
            for option_index, option_text in enumerate(options):
                db.session.add(
                    Option(
                        question_id=question.id,
                        text=option_text,
                        is_correct=option_index == correct,
                        order_index=option_index,
                    )
                )
            order_index += 1
    db.session.commit()
