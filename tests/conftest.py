import re
import sys
from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app, limiter, socketio  # noqa: E402
from app.cli import _add_sample_quiz, upgrade_database  # noqa: E402
from app.models import Quiz, QuizMaster, User, db  # noqa: E402

PASSWORD = "correct-horse-battery"
PASSWORD_HASH = generate_password_hash(PASSWORD, method="pbkdf2:sha256:1000")  # cheap, for speed


@pytest.fixture
def make_app(tmp_path):
    def build(**overrides):
        app = create_app(
            "testing", SQLALCHEMY_DATABASE_URI="sqlite:///" + (tmp_path / "test.db").as_posix(), **overrides
        )
        upgrade_database(app)
        with app.app_context():
            master = QuizMaster(username="host", email="host@example.com")
            rival = QuizMaster(username="rival", email="rival@example.com")
            # Same numeric ids as the quiz masters, on purpose.
            admin = User(username="boss", email="boss@example.com", is_admin=True)
            player = User(username="player", email="player@example.com")
            for account in (master, rival, admin, player):
                account.password_hash = PASSWORD_HASH
                db.session.add(account)
            db.session.commit()
            _add_sample_quiz(master)
        return app

    yield build
    limiter.enabled = False


@pytest.fixture
def app(make_app):
    return make_app()


@pytest.fixture
def login(app):
    def do(name):
        client = app.test_client()
        response = client.post("/auth/login", data={"email": f"{name}@example.com", "password": PASSWORD})
        assert response.status_code == 302
        return client

    return do


@pytest.fixture
def quiz_id(app):
    with app.app_context():
        return Quiz.query.one().id


class Phone:
    def __init__(self, app, code, name):
        self.app, self.code, self.http = app, code, app.test_client()
        self.join_response = self.http.post(f"/play/{code}/join", data={"team_name": name})
        self.socket = None

    @property
    def joined(self):
        return self.join_response.headers.get("Location", "").endswith("/game")

    def connect(self):
        self.socket = socketio.test_client(self.app, flask_test_client=self.http)
        self.socket.emit("join_room", {"session_code": self.code})
        return self

    def events(self):
        return {event["name"]: event["args"][0] for event in self.socket.get_received()}

    def answer(self, option_id):
        return self.socket.emit(
            "submit_answer", {"session_code": self.code, "option_id": option_id}, callback=True
        )


class Game:
    def __init__(self, app, host, quiz_id):
        self.app, self.host = app, host
        location = host.post("/master/session/create", data={"quiz_id": quiz_id}).headers["Location"]
        self.code = re.search(r"/session/(\w+)/", location).group(1)

    def phone(self, name):
        return Phone(self.app, self.code, name)

    def do(self, step):
        return self.host.post(f"/master/session/{self.code}/{step}")


@pytest.fixture
def game(app, login, quiz_id):
    return Game(app, login("host"), quiz_id)
