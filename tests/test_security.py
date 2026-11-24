"""Accounts, production configuration, answer leaks and the quiz editor."""

import re
import sqlite3

import pytest
from sqlalchemy import inspect

from app import create_app, socketio
from app.auth.routes import safe_next
from app.cli import upgrade_database
from app.models import Option, Question, Quiz, QuizAttempt, QuizMaster, TeamAnswer, User, db
from conftest import PASSWORD

KEY = "k" * 64


def quiz_form(**changes):
    form = {
        "title": "New quiz", "category": "x", "difficulty": "easy", "question_count": "1",
        "question_seconds": "20", "time_limit_seconds": "60",
        "question_text_0": "Q", "option_text_0_0": "a", "option_text_0_1": "b", "correct_option_0": "1",
    }
    form.update(changes)
    return form


def edit_form(app, quiz_id, keep=None):
    """The edit form as the browser would submit it, optionally keeping only some questions."""
    with app.app_context():
        quiz = db.session.get(Quiz, quiz_id)
        questions = quiz.questions.all()
        if keep is not None:
            questions = [questions[i] for i in keep]
        form = quiz_form(title=quiz.title, question_count=str(len(questions)))
        for i, question in enumerate(questions):
            form[f"question_id_{i}"] = str(question.id)
            form[f"question_text_{i}"] = question.text
            for o, option in enumerate(question.options):
                form[f"option_text_{i}_{o}"] = option.text
                if option.is_correct:
                    form[f"correct_option_{i}"] = str(o)
        return form


# ── Configuration ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("key", [None, "", "short", "dev-secret-key-change-in-production"])
def test_production_refuses_a_weak_secret(key):
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app("production", SECRET_KEY=key)


def test_production_cookies_proxy_and_headers(tmp_path):
    app = create_app(
        "production", SECRET_KEY=KEY, WTF_CSRF_ENABLED=False, RATELIMIT_ENABLED=False,
        SQLALCHEMY_DATABASE_URI="sqlite:///" + (tmp_path / "p.db").as_posix(),
    )
    upgrade_database(app)
    assert app.debug is False
    with app.app_context():
        master = QuizMaster(username="host", email="host@example.com")
        master.set_password(PASSWORD)
        db.session.add(master)
        db.session.flush()
        db.session.add(Quiz(title="t", created_by=master.id))
        db.session.commit()

    client = app.test_client()
    # What Caddy sends to the app on 127.0.0.1.
    via = {"X-Forwarded-Proto": "https", "X-Forwarded-Host": "quizblitz.cruzegames.store", "X-Forwarded-For": "203.0.113.9"}
    kwargs = {"base_url": "https://quizblitz.cruzegames.store", "headers": via}
    response = client.post("/auth/login", data={"email": "host@example.com", "password": PASSWORD}, **kwargs)
    cookie = response.headers["Set-Cookie"]
    assert "Secure" in cookie and "HttpOnly" in cookie and "SameSite=Lax" in cookie
    assert response.headers["X-Frame-Options"] == "DENY"
    lobby = client.post("/master/session/create", data={"quiz_id": 1}, **kwargs).headers["Location"]
    page = client.get(lobby, **kwargs).text
    assert re.search(r"https://quizblitz\.cruzegames\.store/play/[A-Z0-9]{6}", page)
    assert "http://quizblitz" not in page


def test_local_key_is_not_published(app):
    from config import local_secret_key

    assert len(local_secret_key()) == 64
    assert create_app("development", LOG_DIR=None, SECRET_KEY=None).config["SECRET_KEY"] == local_secret_key()


def test_socket_accepts_only_this_site(app):
    assert socketio.server.eio.cors_allowed_origins is None


# ── Accounts ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("target", [
    "https://evil.example/", "//evil.example", "/\\evil.example", "\\\\evil.example", "evil.example",
    "javascript:alert(1)", "/\t/evil.example", "", None,
])
def test_unsafe_next_rejected(target):
    assert safe_next(target) is None


def test_next_stays_on_site(app):
    def location(target):
        response = app.test_client().post(
            "/auth/login", query_string={"next": target}, data={"email": "host@example.com", "password": PASSWORD}
        )
        return response.headers["Location"]

    assert location("https://evil.example/") == "/master/"
    assert location("/master/quiz/new?x=1") == "/master/quiz/new?x=1"


def test_login_attempts_are_limited(make_app):
    app = make_app(RATELIMIT_ENABLED=True)
    client = app.test_client()

    def attempt(password, email="host@example.com"):
        return client.post("/auth/login", data={"email": email, "password": password}).status_code

    assert [attempt("wrong") for _ in range(8)] == [200] * 8
    assert attempt(PASSWORD) == 429
    # Other accounts on the same network can still log in.
    assert attempt(PASSWORD, "player@example.com") == 302


def test_successful_logins_are_not_limited(make_app):
    app = make_app(RATELIMIT_ENABLED=True)
    for _ in range(12):
        response = app.test_client().post("/auth/login", data={"email": "host@example.com", "password": PASSWORD})
        assert response.status_code == 302


def test_player_cannot_register_a_quiz_masters_email(app):
    response = app.test_client().post("/auth/register", data={
        "username": "sneaky", "email": "HOST@example.com", "password": PASSWORD, "confirm_password": PASSWORD,
    })
    assert response.status_code == 200
    with app.app_context():
        assert User.query.filter_by(username="sneaky").first() is None


def test_create_master_command(app):
    runner = app.test_cli_runner()
    ok = ["create-master", "--username", "new", "--email", "New@Example.com", "--password", PASSWORD]
    assert runner.invoke(args=ok).exit_code == 0
    assert runner.invoke(args=ok).exit_code != 0  # duplicate
    weak = ["create-master", "--username", "w", "--email", "w@example.com", "--password", "short"]
    assert runner.invoke(args=weak).exit_code != 0
    with app.app_context():
        assert QuizMaster.query.filter_by(email="new@example.com").one().check_password(PASSWORD)


def test_set_password_command(app):
    args = ["set-password", "host@example.com", "--password", "another-long-password"]
    assert app.test_cli_runner().invoke(args=args).exit_code == 0
    with app.app_context():
        assert QuizMaster.query.filter_by(username="host").one().check_password("another-long-password")


def test_seed_never_overwrites(app):
    result = app.test_cli_runner().invoke(args=["seed-db"])
    assert result.exit_code != 0
    with app.app_context():
        assert Quiz.query.count() == 1 and User.query.count() == 2


def test_csrf_is_enforced(make_app):
    app = make_app(WTF_CSRF_ENABLED=True)
    response = app.test_client().post("/auth/login", data={"email": "host@example.com", "password": PASSWORD})
    assert b"Welcome back, host" not in response.data and response.status_code != 302


# ── Self-paced quizzes ─────────────────────────────────────────────────────

def test_live_quiz_answers_are_not_available_to_players(login, quiz_id):
    player = login("player")
    assert f"/quiz/{quiz_id}/start" not in player.get("/quiz/").text
    for path in ("play", "start", "results", "leaderboard"):
        assert player.get(f"/quiz/{quiz_id}/{path}").status_code == 404
    assert player.post(f"/quiz/{quiz_id}/submit", data={"answers": "{}"}).status_code == 404


def publish(app, quiz_id):
    with app.app_context():
        db.session.get(Quiz, quiz_id).is_published = True
        db.session.commit()


def test_published_quiz_can_be_played(app, login, quiz_id):
    publish(app, quiz_id)
    player = login("player")
    assert player.get(f"/quiz/{quiz_id}/play").status_code == 200
    response = player.post(f"/quiz/{quiz_id}/submit", data={"answers": "{}"})
    assert player.get(response.headers["Location"]).status_code == 200


@pytest.mark.parametrize("answers", ["[]", "5", "null", '"x"', "{bad"])
def test_malformed_answers(app, login, quiz_id, answers):
    publish(app, quiz_id)
    assert login("player").post(f"/quiz/{quiz_id}/submit", data={"answers": answers}).status_code == 302


def test_quiz_master_cannot_record_attempts(app, login, quiz_id):
    publish(app, quiz_id)
    login("host").post(f"/quiz/{quiz_id}/submit", data={"answers": "{}"})
    with app.app_context():
        assert QuizAttempt.query.count() == 0


def test_question_text_cannot_inject_script(app, login, quiz_id):
    publish(app, quiz_id)
    with app.app_context():
        Question.query.first().text = "x</script><script>alert(1)</script>"
        db.session.commit()
    assert "</script><script>alert(1)" not in login("player").get(f"/quiz/{quiz_id}/play").text


# ── Quiz editor ────────────────────────────────────────────────────────────

def test_master_creates_unpublished_quiz(app, login):
    assert login("host").post("/master/quiz/new", data=quiz_form()).status_code == 302
    with app.app_context():
        quiz = Quiz.query.filter_by(title="New quiz").one()
        assert quiz.is_published is False
        question = quiz.questions.one()
        assert question.time_limit_seconds == 20 and question.correct_option.text == "b"


@pytest.mark.parametrize("changes", [
    {"title": ""}, {"question_seconds": "abc"}, {"time_limit_seconds": "1"}, {"question_count": "0"},
    {"question_count": "51"}, {"question_text_0": ""}, {"option_text_0_1": ""}, {"correct_option_0": "3"},
])
def test_invalid_quiz_is_explained_and_kept(app, login, changes):
    response = login("host").post("/master/quiz/new", data=quiz_form(description="my long work", **changes))
    assert response.status_code == 200 and "my long work" in response.text and "flash--danger" in response.text
    with app.app_context():
        assert Quiz.query.count() == 1


def test_admin_quiz_needs_a_quiz_master(app, login):
    admin = login("boss")
    assert admin.get("/admin/quiz/new").status_code == 200
    assert admin.post("/admin/quiz/new", data=quiz_form()).status_code == 200  # refused
    with app.app_context():
        rival_id = QuizMaster.query.filter_by(username="rival").one().id
    assert admin.post("/admin/quiz/new", data=quiz_form(owner_id=rival_id)).status_code == 302
    assert "New quiz" in login("rival").get("/master/").text
    assert "New quiz" not in login("host").get("/master/").text


def test_master_cannot_edit_another_masters_quiz(login, quiz_id):
    assert login("rival").get(f"/master/quiz/{quiz_id}/edit").status_code == 404


def test_editing_keeps_recorded_answers_and_rounds(app, game, quiz_id):
    phone = game.phone("Alpha").connect()
    game.do("start")
    with app.app_context():
        option_id = Question.query.order_by(Question.order_index).first().correct_option.id
    phone.answer(option_id)

    blocked = game.host.post(f"/master/quiz/{quiz_id}/edit", data=edit_form(app, quiz_id), follow_redirects=True)
    assert "being played now" in blocked.text

    game.do("end")
    form = edit_form(app, quiz_id, keep=range(14))  # drop the last question
    form["question_text_0"] = "Reworded"
    assert game.host.post(f"/master/quiz/{quiz_id}/edit", data=form).status_code == 302
    with app.app_context():
        quiz = db.session.get(Quiz, quiz_id)
        assert quiz.questions.count() == 14 and Option.query.count() == 56
        assert quiz.questions.first().text == "Reworded"
        assert [q.round_number for q in quiz.questions] == [1] * 5 + [2] * 5 + [3] * 4
        answer = TeamAnswer.query.one()
        assert db.session.get(Question, answer.question_id) and db.session.get(Option, answer.option_id)

    # Removing the answered question removes its answers too.
    game.host.post(f"/master/quiz/{quiz_id}/edit", data=edit_form(app, quiz_id, keep=range(1, 14)))
    with app.app_context():
        assert TeamAnswer.query.count() == 0


# ── Database ───────────────────────────────────────────────────────────────

def test_upgrade_matches_models_and_keeps_old_data(tmp_path):
    path = tmp_path / "old.db"
    app = create_app("testing", SQLALCHEMY_DATABASE_URI="sqlite:///" + path.as_posix())
    upgrade_database(app)
    with app.app_context():
        from flask_migrate import downgrade

        db.session.add(QuizMaster(username="m", email="m@example.com", password_hash="x"))
        db.session.commit()
        db.session.remove()
        downgrade(revision="0001")
        db.engine.dispose()
    # A database from before migrations existed.
    with sqlite3.connect(path) as connection:
        connection.execute("DROP TABLE alembic_version")
    connection.close()

    upgrade_database(app)
    upgrade_database(app)  # repeatable
    with app.app_context():
        assert QuizMaster.query.one().username == "m"
        inspector = inspect(db.engine)
        for table in db.metadata.sorted_tables:
            assert {c["name"] for c in inspector.get_columns(table.name)} == set(table.columns.keys())
        assert "uq_team_session_name_ci" in {
            row[0] for row in db.session.execute(db.text("select name from sqlite_master where type='index'"))
        }


def test_health(app):
    assert app.test_client().get("/health").json == {"status": "ok", "database": "connected"}
