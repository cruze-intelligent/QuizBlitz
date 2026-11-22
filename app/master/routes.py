from collections import Counter
from datetime import datetime, timezone
import base64
import io

import qrcode
from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import case, func

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
    if question is None:
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
        return render_template("master/question.html", options=options, answers_in=answers_in, **context)

    if game_session.state == "reveal":
        return render_template("master/reveal.html", reveal=_reveal_summary(game_session, question), **context)

    return render_template(
        "master/leaderboard.html",
        rankings=_rankings(game_session),
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

    started = _transition(
        game_session,
        ["lobby"],
        "question",
        current_question_index=0,
        started_at=datetime.now(timezone.utc),
    )
    if not started:
        flash("This session has already started.", "warning")
        return _screen(code)

    current_app.logger.info("Session %s started by %s", code, current_user.username)
    socketio.emit("session_started", {}, room=code)
    _push_question(game_session)
    return _screen(code)


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

    summary = _reveal_summary(game_session, question)
    payload = {key: summary[key] for key in (
        "correct_option_id", "correct_option_text", "passed_count", "failed_count", "team_results",
    )}
    socketio.emit("answer_revealed", payload, room=code)
    return _screen(code)


@master_bp.route("/session/<code>/next", methods=["POST"])
@login_required
def next_question(code: str):
    """Advance the state machine: REVEAL → LEADERBOARD → next QUESTION (or FINISHED)."""
    game_session = _get_owned_session(code)
    question_total = game_session.quiz.question_count

    if game_session.state == "reveal":
        if _transition(game_session, ["reveal"], "leaderboard"):
            rankings = _public_rankings(_rankings(game_session))
            socketio.emit("leaderboard_updated", {"rankings": rankings}, room=code)
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
        if _transition(game_session, ["leaderboard"], "finished", ended_at=datetime.now(timezone.utc)):
            current_app.logger.info("Session %s finished by %s", code, current_user.username)
            final_rankings = _public_rankings(_rankings(game_session))
            socketio.emit("session_finished", {"final_rankings": final_rankings}, room=code)
        return _screen(code)

    if _transition(game_session, ["leaderboard"], "question", current_question_index=next_index):
        _push_question(game_session)
    return _screen(code)


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


def _reveal_summary(game_session: GameSession, question: Question) -> dict:
    """Results for a revealed question: correct option, per-option pick counts and
    each team's outcome. Teams that didn't answer count as failed (spec)."""
    correct = question.correct_option
    answers = {answer.team_id: answer for answer in game_session.answers_for(question).all()}
    picks = Counter(answer.option_id for answer in answers.values())

    team_results = []
    for team in game_session.teams.order_by(Team.joined_at.asc()).all():
        answer = answers.get(team.id)
        team_results.append({
            "team_name": team.team_name,
            "is_correct": bool(answer and answer.is_correct),
            "answered": answer is not None,
        })
    passed = sum(result["is_correct"] for result in team_results)

    return {
        "correct_option_id": correct.id if correct else None,
        "correct_option_text": correct.text if correct else "",
        "passed_count": passed,
        "failed_count": len(team_results) - passed,
        "team_results": team_results,
        "options": [
            {"id": option.id, "text": option.text, "is_correct": option.is_correct, "count": picks.get(option.id, 0)}
            for option in question.options.order_by(Option.order_index).all()
        ],
    }


def _rankings(game_session: GameSession) -> list[dict]:
    """Leaderboard rows, best first.

    - rank: standard competition ranking, so tied scores share a rank (1, 1, 3).
    - score_delta: points gained on the most recently revealed question.
    - prev_index / movement: position and rank change versus the standings before that
      question, used to animate rows into their new order. There are no previous
      standings before the first question, so nothing moves then.
    """
    teams = game_session.teams.order_by(Team.joined_at.asc()).all()
    question = game_session.current_question()
    gained = {}
    if question is not None and game_session.state in ("reveal", "leaderboard", "finished"):
        correct_answers = game_session.answers_for(question).filter(TeamAnswer.is_correct.is_(True))
        gained = {answer.team_id: question.points for answer in correct_answers}
    has_previous = game_session.current_question_index > 0

    rows = []
    for team in teams:
        delta = gained.get(team.id, 0)
        rows.append({"team_name": team.team_name, "score": team.score, "delta": delta, "prev_score": team.score - delta})
    # sorted() is stable, so equal scores keep join order (then previous position).
    for index, row in enumerate(sorted(rows, key=lambda r: -r["prev_score"])):
        row["prev_index"] = index
    ordered = sorted(rows, key=lambda r: (-r["score"], r["prev_index"]))

    scores = [row["score"] for row in rows]
    prev_scores = [row["prev_score"] for row in rows]
    rankings = []
    for index, row in enumerate(ordered):
        rank = 1 + sum(score > row["score"] for score in scores)
        prev_rank = 1 + sum(score > row["prev_score"] for score in prev_scores)
        rankings.append({
            "rank": rank,
            "team_name": row["team_name"],
            "score": row["score"],
            "score_delta": row["delta"],
            "prev_index": row["prev_index"] if has_previous else index,
            "movement": (prev_rank - rank) if has_previous else 0,
        })
    return rankings


def _public_rankings(rankings: list[dict]) -> list[dict]:
    """Rankings in the socket payload shape from the spec."""
    return [{key: row[key] for key in ("rank", "team_name", "score", "score_delta")} for row in rankings]
