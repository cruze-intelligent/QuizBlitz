from datetime import datetime, timezone
import base64
import io

import qrcode
from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import socketio
from app.models import GameSession, Option, Question, Quiz, QuizAttempt, QuizMaster, Team, TeamAnswer, db

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
    import random
    import string

    alphabet = string.ascii_uppercase + string.digits
    while True:
        code = "".join(random.choice(alphabet) for _ in range(6))
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
    average_score = 0.0
    if total_attempts:
        average_score = round(sum(attempt.score for attempt in QuizAttempt.query.all()) / total_attempts, 1)

    stats = {
        "total_quizzes": len(quizzes),
        "live_sessions": GameSession.query.count(),
        "attempts": total_attempts,
        "avg_score": average_score,
    }

    return render_template(
        "master/dashboard.html",
        quizzes=quizzes,
        stats=stats,
        search=search,
        title="Master Dashboard",
    )


@master_bp.route("/quiz/new", methods=["GET", "POST"])
@login_required
def create_quiz():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        if not title:
            flash("Quiz title is required.", "danger")
            return redirect(url_for("master.create_quiz"))

        num_questions = request.form.get("question_count", default=1, type=int)
        if num_questions is None or not 1 <= num_questions <= 50:
            flash("A quiz must have between 1 and 50 questions.", "danger")
            return redirect(url_for("master.create_quiz"))

        question_data = []
        for idx in range(num_questions):
            question_text = request.form.get(f"question_text_{idx}", "").strip()
            options = [
                request.form.get(f"option_text_{idx}_{option_idx}", "").strip()
                for option_idx in range(4)
            ]
            correct_option = request.form.get(f"correct_option_{idx}", type=int)
            if not question_text or any(not option for option in options):
                flash(f"Question {idx + 1} and all four answer options are required.", "danger")
                return redirect(url_for("master.create_quiz"))
            if correct_option not in range(4):
                flash(f"Choose the correct answer for question {idx + 1}.", "danger")
                return redirect(url_for("master.create_quiz"))
            question_data.append((question_text, options, correct_option))

        quiz = Quiz(
            title=title,
            description=request.form.get("description", "").strip(),
            category=request.form.get("category", "General").strip() or "General",
            difficulty=request.form.get("difficulty", "easy").strip() or "easy",
            time_limit_seconds=int(request.form.get("time_limit_seconds", 30) or 30),
            is_published=True,
            created_by=current_user.id,
        )
        db.session.add(quiz)
        db.session.flush()

        for idx, (question_text, options, correct_option) in enumerate(question_data):
            question = Question(
                quiz_id=quiz.id,
                text=question_text,
                order_index=idx,
                round_number=1,
                order_in_round=idx + 1,
                time_limit_seconds=30,
                points=10,
            )
            db.session.add(question)
            db.session.flush()
            for opt_idx, option_text in enumerate(options):
                db.session.add(
                    Option(
                        question_id=question.id,
                        text=option_text,
                        is_correct=opt_idx == correct_option,
                        order_index=opt_idx,
                    )
                )

        db.session.commit()
        current_app.logger.info("Quiz created by %s: %s", current_user.username, quiz.title)
        flash("Quiz created successfully.", "success")
        return redirect(url_for("master.dashboard"))

    return render_template(
        "admin/quiz_form.html",
        quiz=None,
        title="Create Quiz",
        action=url_for("master.create_quiz"),
        back_url=url_for("master.dashboard"),
    )


@master_bp.route("/session/create", methods=["GET", "POST"])
@login_required
def create_session():
    if request.method == "GET":
        return redirect(url_for("master.dashboard"))

    quiz = _get_owned_quiz(request.form.get("quiz_id", type=int))

    session_code = _generate_session_code()
    join_url = f"{request.host_url.rstrip('/')}play/{session_code}"
    qr = qrcode.make(join_url)
    buffer = io.BytesIO()
    qr.save(buffer, format="PNG")
    qr_b64 = base64.b64encode(buffer.getvalue()).decode("ascii")

    game_session = GameSession(
        session_code=session_code,
        quiz_id=quiz.id,
        state="lobby",
        current_question_index=0,
        started_at=None,
        ended_at=None,
        qr_b64=qr_b64,
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
    teams = game_session.teams.order_by(Team.joined_at.asc()).all()
    return render_template("master/lobby.html", session=game_session, teams=teams, title=f"Lobby — {code}")


@master_bp.route("/session/<code>/start", methods=["POST"])
@login_required
def start_session(code: str):
    game_session = _get_owned_session(code)
    if game_session.quiz.question_count == 0:
        flash("This quiz has no questions.", "warning")
        return redirect(url_for("master.lobby", code=code))

    started = _transition(
        game_session,
        ["lobby"],
        "question",
        current_question_index=0,
        started_at=datetime.now(timezone.utc),
    )
    if not started:
        flash("This session has already started.", "warning")
        return redirect(url_for("master.lobby", code=code))

    current_app.logger.info("Session %s started by %s", code, current_user.username)
    socketio.emit("session_started", {}, room=code)
    _push_question(game_session)
    return redirect(url_for("master.lobby", code=code))


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
        return redirect(url_for("master.lobby", code=code))

    correct_option = question.correct_option
    team_results = []
    passed_count = 0
    failed_count = 0

    for team in game_session.teams.all():
        answer = TeamAnswer.query.filter_by(team_id=team.id, question_id=question.id).first()
        is_correct = bool(answer and answer.option_id == correct_option.id) if correct_option else False
        if is_correct:
            passed_count += 1
            team.score += question.points
        else:
            failed_count += 1
        if answer is not None:
            answer.is_correct = is_correct
            db.session.add(answer)
        team_results.append({"team_name": team.team_name, "is_correct": is_correct})

    db.session.commit()
    current_app.logger.info("Answer revealed for session %s on question %s", code, question.id)

    payload = {
        "correct_option_id": correct_option.id if correct_option else None,
        "correct_option_text": correct_option.text if correct_option else "",
        "passed_count": passed_count,
        "failed_count": failed_count,
        "team_results": team_results,
    }
    socketio.emit("answer_revealed", payload, room=code)
    return redirect(url_for("master.lobby", code=code))


@master_bp.route("/session/<code>/next", methods=["POST"])
@login_required
def next_question(code: str):
    """Advance the state machine: REVEAL → LEADERBOARD → next QUESTION (or FINISHED)."""
    game_session = _get_owned_session(code)
    question_total = game_session.quiz.question_count
    lobby_url = url_for("master.lobby", code=code)

    if game_session.state == "reveal":
        if _transition(game_session, ["reveal"], "leaderboard"):
            rankings = _leaderboard_payload(game_session)
            socketio.emit("leaderboard_updated", {"rankings": rankings}, room=code)
        return redirect(lobby_url)

    if game_session.state != "leaderboard":
        messages = {
            "lobby": "Start the quiz first.",
            "question": "Reveal the answer before moving on.",
            "finished": "This session has finished.",
        }
        flash(messages.get(game_session.state, "Can't advance from here."), "warning")
        return redirect(lobby_url)

    next_index = game_session.current_question_index + 1
    if next_index >= question_total:
        if _transition(game_session, ["leaderboard"], "finished", ended_at=datetime.now(timezone.utc)):
            current_app.logger.info("Session %s finished by %s", code, current_user.username)
            socketio.emit("session_finished", {"final_rankings": _leaderboard_payload(game_session)}, room=code)
        return redirect(lobby_url)

    if _transition(game_session, ["leaderboard"], "question", current_question_index=next_index):
        _push_question(game_session)
    return redirect(lobby_url)


def _push_question(game_session: GameSession):
    question = game_session.current_question()
    if not question:
        return
    payload = {
        "question_text": question.text,
        "options": [{"id": option.id, "text": option.text} for option in question.options.order_by(Option.order_index).all()],
        "round": question.round_number,
        "question_num": question.order_in_round,
        "total_questions": game_session.quiz.question_count,
        "time_limit_seconds": question.time_limit_seconds,
    }
    socketio.emit("question_pushed", payload, room=game_session.session_code)


def _leaderboard_payload(game_session: GameSession):
    teams = game_session.teams.order_by(Team.score.desc(), Team.joined_at.asc()).all()
    rankings = []
    for rank, team in enumerate(teams, start=1):
        previous_score = team.score
        rankings.append({
            "rank": rank,
            "team_name": team.team_name,
            "score": team.score,
            "score_delta": 0,
        })
        team.score = previous_score
    return rankings
