import base64
import io
import secrets
import time
from datetime import datetime, timezone

import qrcode
from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import case, func

from app import socketio
from app.game import public_rankings, question_payload, rankings, reveal_payload, reveal_summary, sequence
from app.models import GameSession, Option, Quiz, QuizAttempt, QuizMaster, Team, db
from app.quiz import editor

master_bp = Blueprint("master", __name__)


@master_bp.before_request
@login_required
def _require_quiz_master():
    """Live-game routes are for QuizMaster accounts only (not regular users or admins)."""
    if not isinstance(current_user._get_current_object(), QuizMaster):
        from app.auth.routes import home_url

        flash("Only quiz master accounts can run live sessions.", "warning")
        return redirect(home_url())
    return None


def _get_owned_quiz(quiz_id) -> Quiz:
    quiz = db.session.get(Quiz, quiz_id) if quiz_id else None
    if quiz is None or quiz.created_by != current_user.id:
        abort(404)
    return quiz


def _get_owned_session(code: str) -> GameSession:
    """Fetch a session the current quiz master owns; 404 otherwise so codes aren't probeable."""
    game_session = GameSession.query.filter_by(session_code=code).first_or_404()
    if game_session.quiz is None or game_session.quiz.created_by != current_user.id:
        abort(404)
    return game_session


def _transition(game_session: GameSession, from_states, to_state: str, **fields) -> bool:
    """Atomically move the session to `to_state` only if it's currently in `from_states`.

    The conditional UPDATE means a double-click or two concurrent requests can't both
    win, so side effects (scoring, pushing questions) run at most once per transition.
    """
    updated = (
        GameSession.query.filter(GameSession.id == game_session.id, GameSession.state.in_(from_states))
        .update({"state": to_state, **fields}, synchronize_session=False)
    )
    db.session.commit()
    if updated:
        db.session.refresh(game_session)
    return bool(updated)


def _generate_session_code() -> str:
    # No 0/O or 1/I: codes get read off a projector and typed on a phone.
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    while True:
        code = "".join(secrets.choice(alphabet) for _ in range(6))
        if not db.session.query(GameSession).filter_by(session_code=code).first():
            return code


@master_bp.route("/", methods=["GET"])
@login_required
def dashboard():
    search = request.args.get("q", "").strip()
    quiz_query = Quiz.query.filter(Quiz.created_by == current_user.id)

    if search:
        quiz_query = quiz_query.filter(Quiz.title.ilike(f"%{search}%"))

    quizzes = quiz_query.order_by(Quiz.created_at.desc()).all()

    total_attempts = QuizAttempt.query.count()
    # Mean of per-attempt percentages (same rule as QuizAttempt.percentage: 0% when no
    # points were available). Averaging raw `score` produced points, shown as e.g. "120.0%".
    attempt_pct = case(
        (QuizAttempt.total_points > 0, QuizAttempt.score * 100.0 / QuizAttempt.total_points),
        else_=0.0,
    )
    average_score = round(db.session.query(func.avg(attempt_pct)).scalar() or 0.0, 1)

    stats = {
        "total_quizzes": len(quizzes),
        "live_sessions": GameSession.query.count(),
        "attempts": total_attempts,
        "avg_score": average_score,
    }

    active_sessions = (
        GameSession.query.join(Quiz)
        .filter(Quiz.created_by == current_user.id, GameSession.state.in_(GameSession.ACTIVE_STATES))
        .order_by(GameSession.id.desc())
        .all()
    )

    return render_template(
        "master/dashboard.html",
        quizzes=quizzes,
        active_sessions=active_sessions,
        stats=stats,
        search=search,
        title="Master Dashboard",
    )


@master_bp.route("/quiz/new", methods=["GET", "POST"])
@login_required
def create_quiz():
    form = editor.blank_form()
    if request.method == "POST":
        form, errors = editor.parse_form(request.form)
        if not errors:
            quiz = Quiz(created_by=current_user.id)
            editor.save(quiz, form)
            current_app.logger.info("Quiz created by %s: %s", current_user.username, quiz.title)
            flash("Quiz created successfully.", "success")
            return redirect(url_for("master.dashboard"))
        _flash_errors(errors)

    return _quiz_form(form, "Create Quiz", url_for("master.create_quiz"), is_new=True)


@master_bp.route("/quiz/<int:quiz_id>/edit", methods=["GET", "POST"])
@login_required
def edit_quiz(quiz_id: int):
    quiz = _get_owned_quiz(quiz_id)
    game = editor.active_game(quiz)
    if game:
        flash(f"This quiz is being played now (game {game.session_code}). Edit it after the game ends.", "warning")
        return redirect(url_for("master.dashboard"))

    form = editor.form_from_quiz(quiz)
    if request.method == "POST":
        form, errors = editor.parse_form(request.form)
        if not errors:
            editor.save(quiz, form)
            current_app.logger.info("Quiz edited by %s: %s", current_user.username, quiz.title)
            flash("Quiz updated.", "success")
            return redirect(url_for("master.dashboard"))
        _flash_errors(errors)

    return _quiz_form(form, "Edit Quiz", url_for("master.edit_quiz", quiz_id=quiz_id), is_new=False)


def _flash_errors(errors: list[str]) -> None:
    for error in errors:
        flash(error, "danger")


def _quiz_form(form: dict, title: str, action: str, is_new: bool):
    return render_template(
        "admin/quiz_form.html",
        form=form,
        is_new=is_new,
        title=title,
        action=action,
        back_url=url_for("master.dashboard"),
    )


@master_bp.route("/session/create", methods=["GET", "POST"])
@login_required
def create_session():
    if request.method == "GET":
        return redirect(url_for("master.dashboard"))

    quiz = _get_owned_quiz(request.form.get("quiz_id", type=int))

    session_code = _generate_session_code()

    # qr_b64 is no longer stored: the lobby builds the QR from the host the master is
    # actually browsing on (see _join_qr), so it is always reachable from phones.
    game_session = GameSession(
        session_code=session_code,
        quiz_id=quiz.id,
        state="lobby",
        current_question_index=0,
        started_at=None,
        ended_at=None,
    )
    db.session.add(game_session)
    db.session.commit()

    current_app.logger.info("Session %s created for quiz %s by %s", session_code, quiz.title, current_user.username)
    flash(f"Session {session_code} created.", "success")
    return redirect(url_for("master.lobby", code=game_session.session_code))


@master_bp.route("/session/<code>/lobby", methods=["GET"])
@login_required
def lobby(code: str):
    game_session = _get_owned_session(code)
    if game_session.state != "lobby":
        return _screen(code)
    teams = game_session.teams.order_by(Team.joined_at.asc()).all()
    join_url, qr_b64 = _join_qr(game_session.session_code)
    return render_template(
        "master/lobby.html",
        session=game_session,
        teams=teams,
        join_url=join_url,
        qr_b64=qr_b64,
        title=f"Lobby — {code}",
    )


@master_bp.route("/session/<code>", methods=["GET"])
@login_required
def session_screen(code: str):
    """The quiz master's screen for the session's current state.

    Every state transition (POST) redirects here, so a refresh always shows the right
    screen: question → reveal → leaderboard → … → finished (final leaderboard).
    """
    game_session = _get_owned_session(code)
    if game_session.state == "lobby":
        return redirect(url_for("master.lobby", code=code))

    question = game_session.current_question()
    if question is None and game_session.state != "finished":
        abort(404)
    total = game_session.quiz.question_count
    context = {
        "session": game_session,
        "question": question,
        "question_number": game_session.current_question_index + 1,
        "total_questions": total,
        "is_last_question": game_session.current_question_index + 1 >= total,
        "team_count": game_session.team_count,
        "join_url": url_for("play.join_form", session_code=game_session.session_code, _external=True),
    }

    if game_session.state == "question":
        # Display only: the projector is visible to the teams, so no answer key here.
        options = question.options.order_by(Option.order_index).all()
        answers_in = game_session.answers_for(question).count()
        return render_template(
            "master/question.html",
            options=options,
            answers_in=answers_in,
            remaining_ms=game_session.remaining_ms(),
            **context,
        )

    if game_session.state == "reveal":
        return render_template("master/reveal.html", reveal=reveal_summary(game_session, question), **context)

    return render_template(
        "master/leaderboard.html",
        rankings=rankings(game_session),
        is_final=game_session.state == "finished",
        **context,
    )


def _screen(code: str):
    return redirect(url_for("master.session_screen", code=code))


def _join_qr(session_code: str):
    """Team join URL and its QR code (base64 PNG) for the current request's host.

    Built per request rather than stored at creation, so the QR always matches the
    address the master's browser is using (e.g. the laptop's Wi-Fi IP for phones).
    """
    join_url = url_for("play.join_form", session_code=session_code, _external=True)
    buffer = io.BytesIO()
    qrcode.make(join_url).save(buffer, format="PNG")
    return join_url, base64.b64encode(buffer.getvalue()).decode("ascii")


@master_bp.route("/session/<code>/start", methods=["POST"])
@login_required
def start_session(code: str):
    game_session = _get_owned_session(code)
    if game_session.quiz.question_count == 0:
        flash("This quiz has no questions.", "warning")
        return _screen(code)

    started = _open_question(game_session, "lobby", 0, started_at=datetime.now(timezone.utc))
    if not started:
        flash("This session has already started.", "warning")
        return _screen(code)

    current_app.logger.info("Session %s started by %s", code, current_user.username)
    socketio.emit("session_started", {}, room=code)
    _push_question(game_session)
    return _screen(code)


def _open_question(game_session: GameSession, from_state: str, index: int, **fields) -> bool:
    """Move to QUESTION at `index` and start its clock."""
    questions = game_session.quiz.questions.all()
    seconds = questions[index].time_limit_seconds
    return _transition(
        game_session,
        [from_state],
        "question",
        current_question_index=index,
        question_deadline=time.time() + seconds if seconds else None,
        **fields,
    )


def _push_question(game_session: GameSession) -> None:
    question = game_session.current_question()
    if question:
        payload = question_payload(game_session, question)
        socketio.emit("question_pushed", payload, room=game_session.session_code)


def _finish(game_session: GameSession, from_states) -> bool:
    if not _transition(game_session, from_states, "finished", ended_at=datetime.now(timezone.utc)):
        return False
    code = game_session.session_code
    current_app.logger.info("Session %s finished by %s", code, current_user.username)
    payload = {"seq": sequence(game_session), "final_rankings": public_rankings(game_session)}
    socketio.emit("session_finished", payload, room=code)
    return True


@master_bp.route("/session/<code>/end", methods=["POST"])
@login_required
def end_session(code: str):
    """Close a game early (or an unused lobby). Scores so far become the final results."""
    game_session = _get_owned_session(code)
    if _finish(game_session, GameSession.ACTIVE_STATES):
        flash(f"Game {code} ended.", "success")
    return redirect(url_for("master.dashboard"))


@master_bp.route("/session/<code>/reveal", methods=["POST"])
@login_required
def reveal_answer(code: str):
    game_session = _get_owned_session(code)
    question = game_session.current_question()
    if not question:
        abort(404)

    # Only one reveal per question: scoring below must never run twice.
    if not _transition(game_session, ["question"], "reveal"):
        flash("There's no open question to reveal right now.", "warning")
        return _screen(code)

    correct_option = question.correct_option
    for answer in game_session.answers_for(question).all():
        answer.is_correct = bool(correct_option and answer.option_id == correct_option.id)
        if answer.is_correct:
            answer.team.score += question.points
    db.session.commit()
    current_app.logger.info("Answer revealed for session %s on question %s", code, question.id)

    socketio.emit("answer_revealed", reveal_payload(game_session, question), room=code)
    return _screen(code)


@master_bp.route("/session/<code>/next", methods=["POST"])
@login_required
def next_question(code: str):
    """Advance the state machine: REVEAL → LEADERBOARD → next QUESTION (or FINISHED)."""
    game_session = _get_owned_session(code)
    question_total = game_session.quiz.question_count

    if game_session.state == "reveal":
        if _transition(game_session, ["reveal"], "leaderboard"):
            payload = {"seq": sequence(game_session), "rankings": public_rankings(game_session)}
            socketio.emit("leaderboard_updated", payload, room=code)
        return _screen(code)

    if game_session.state != "leaderboard":
        messages = {
            "lobby": "Start the quiz first.",
            "question": "Reveal the answer before moving on.",
            "finished": "This session has finished.",
        }
        flash(messages.get(game_session.state, "Can't advance from here."), "warning")
        return _screen(code)

    next_index = game_session.current_question_index + 1
    if next_index >= question_total:
        _finish(game_session, ["leaderboard"])
        return _screen(code)

    if _open_question(game_session, "leaderboard", next_index):
        _push_question(game_session)
    return _screen(code)
