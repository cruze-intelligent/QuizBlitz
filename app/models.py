"""app/models.py — ORM models for the QuizBlitz app."""

from datetime import datetime, timezone

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash

db = SQLAlchemy()


class User(UserMixin, db.Model):
    """Authenticated quiz master account."""

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    attempts = db.relationship("QuizAttempt", backref="user", lazy="dynamic")

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def __repr__(self) -> str:
        return f"<User {self.username}>"


class QuizMaster(UserMixin, db.Model):
    """Quiz master account used by the live game admin workflow."""

    __tablename__ = "quiz_masters"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    quizzes = db.relationship("Quiz", backref="master", lazy="dynamic", foreign_keys="Quiz.created_by")

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def __repr__(self) -> str:
        return f"<QuizMaster {self.username}>"


class Quiz(db.Model):
    """Quiz metadata and question collection."""

    __tablename__ = "quizzes"

    DIFFICULTY_CHOICES = ["easy", "medium", "hard"]

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(128), nullable=False)
    description = db.Column(db.Text, default="")
    category = db.Column(db.String(64), default="General")
    difficulty = db.Column(db.String(16), default="easy")
    time_limit_seconds = db.Column(db.Integer, default=180)
    is_published = db.Column(db.Boolean, default=False, nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey("quiz_masters.id"), nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    questions = db.relationship(
        "Question",
        backref="quiz",
        lazy="dynamic",
        order_by="Question.order_index",
        cascade="all, delete-orphan",
    )
    attempts = db.relationship("QuizAttempt", backref="quiz", lazy="dynamic", cascade="all, delete-orphan")
    sessions = db.relationship("GameSession", backref="quiz", lazy="dynamic", cascade="all, delete-orphan")

    @property
    def question_count(self) -> int:
        return self.questions.count()

    @property
    def total_points(self) -> int:
        return sum(q.points for q in self.questions)

    def __repr__(self) -> str:
        return f"<Quiz {self.title}>"


class Question(db.Model):
    """A question in a quiz, optionally grouped by round."""

    __tablename__ = "questions"

    id = db.Column(db.Integer, primary_key=True)
    quiz_id = db.Column(db.Integer, db.ForeignKey("quizzes.id"), nullable=False)
    text = db.Column(db.Text, nullable=False)
    round_number = db.Column(db.Integer, default=1)
    order_in_round = db.Column(db.Integer, default=0)
    order_index = db.Column(db.Integer, default=0)
    time_limit_seconds = db.Column(db.Integer, default=30)
    points = db.Column(db.Integer, default=10)

    options = db.relationship(
        "Option",
        backref="question",
        lazy="dynamic",
        order_by="Option.order_index",
        cascade="all, delete-orphan",
    )

    @property
    def correct_option(self):
        return self.options.filter_by(is_correct=True).first()

    def __repr__(self) -> str:
        return f"<Question {self.id}: {self.text[:40]}>"


class Option(db.Model):
    """An answer choice for a Question."""

    __tablename__ = "options"

    id = db.Column(db.Integer, primary_key=True)
    question_id = db.Column(db.Integer, db.ForeignKey("questions.id"), nullable=False)
    text = db.Column(db.String(256), nullable=False)
    is_correct = db.Column(db.Boolean, default=False, nullable=False)
    order_index = db.Column(db.Integer, default=0)

    def __repr__(self) -> str:
        return f"<Option {self.id}: {self.text[:30]} ({'✓' if self.is_correct else '✗'})>"


class GameSession(db.Model):
    """A live game session tied to a quiz."""

    __tablename__ = "game_sessions"
    __table_args__ = (
        db.UniqueConstraint("session_code", name="uq_game_session_session_code"),
    )

    id = db.Column(db.Integer, primary_key=True)
    session_code = db.Column(db.String(6), nullable=False, index=True)
    quiz_id = db.Column(db.Integer, db.ForeignKey("quizzes.id"), nullable=False)
    state = db.Column(db.String(32), default="lobby", nullable=False)
    current_question_index = db.Column(db.Integer, default=0, nullable=False)
    started_at = db.Column(db.DateTime)
    ended_at = db.Column(db.DateTime)
    qr_b64 = db.Column(db.Text)

    teams = db.relationship("Team", backref="session", lazy="dynamic", cascade="all, delete-orphan")

    @property
    def team_count(self) -> int:
        return self.teams.count()

    def current_question(self):
        if not self.quiz_id:
            return None
        quiz = db.session.get(Quiz, self.quiz_id)
        if not quiz:
            return None
        question_list = list(quiz.questions.order_by(Question.order_index).all())
        if not question_list:
            return None
        idx = min(max(self.current_question_index, 0), len(question_list) - 1)
        return question_list[idx]

    def __repr__(self) -> str:
        return f"<GameSession {self.session_code}: {self.state}>"


class Team(db.Model):
    """A team participating in a live quiz session."""

    __tablename__ = "teams"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("game_sessions.id"), nullable=False)
    team_name = db.Column(db.String(120), nullable=False)
    score = db.Column(db.Integer, default=0, nullable=False)
    joined_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    answers = db.relationship("TeamAnswer", backref="team", lazy="dynamic", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Team {self.team_name}>"


class TeamAnswer(db.Model):
    """A single answer submission from a team to one question."""

    __tablename__ = "team_answers"
    __table_args__ = (
        db.UniqueConstraint("team_id", "question_id", name="uq_team_answer_team_question"),
    )

    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, db.ForeignKey("teams.id"), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey("questions.id"), nullable=False)
    option_id = db.Column(db.Integer, db.ForeignKey("options.id"), nullable=True)
    is_correct = db.Column(db.Boolean, default=False, nullable=False)
    answered_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self) -> str:
        return f"<TeamAnswer team={self.team_id} question={self.question_id}>"


class QuizAttempt(db.Model):
    """Records a completed quiz run by a user."""

    __tablename__ = "quiz_attempts"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    quiz_id = db.Column(db.Integer, db.ForeignKey("quizzes.id"), nullable=False)
    score = db.Column(db.Integer, default=0)
    total_points = db.Column(db.Integer, default=0)
    time_taken_seconds = db.Column(db.Integer, default=0)
    completed_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    @property
    def percentage(self) -> float:
        if self.total_points == 0:
            return 0.0
        return round((self.score / self.total_points) * 100, 1)

    def __repr__(self) -> str:
        return f"<QuizAttempt user={self.user_id} quiz={self.quiz_id} score={self.score}>"
