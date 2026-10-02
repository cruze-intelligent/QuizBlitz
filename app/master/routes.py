from datetime import datetime, timezone
import base64
import io

import qrcode
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import socketio
from app.models import GameSession, Option, Question, Quiz, Team, TeamAnswer, db

master_bp = Blueprint("master", __name__)


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
    quizzes = Quiz.query.order_by(Quiz.created_at.desc()).all()
    return render_template("master/dashboard.html", quizzes=quizzes, title="Master Dashboard")


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

    quiz_id = request.form.get("quiz_id", type=int)
    quiz = db.session.get(Quiz, quiz_id)
    if not quiz:
        abort(404)

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

    flash(f"Session {session_code} created.", "success")
    return redirect(url_for("master.lobby", code=game_session.session_code))


@master_bp.route("/session/<code>/lobby", methods=["GET"])
@login_required
def lobby(code: str):
    game_session = GameSession.query.filter_by(session_code=code).first_or_404()
    teams = game_session.teams.order_by(Team.joined_at.asc()).all()
    return render_template("master/lobby.html", session=game_session, teams=teams, title=f"Lobby — {code}")


@master_bp.route("/session/<code>/start", methods=["POST"])
@login_required
def start_session(code: str):
    game_session = GameSession.query.filter_by(session_code=code).first_or_404()
    game_session.state = "question"
    game_session.current_question_index = 0
    game_session.started_at = datetime.now(timezone.utc)
    db.session.commit()
    socketio.emit("session_started", {}, room=code)
    _push_question(game_session)
    return redirect(url_for("master.lobby", code=code))


@master_bp.route("/session/<code>/reveal", methods=["POST"])
@login_required
def reveal_answer(code: str):
    game_session = GameSession.query.filter_by(session_code=code).first_or_404()
    question = game_session.current_question()
    if not question:
        abort(404)

    game_session.state = "reveal"
    db.session.commit()

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
    game_session = GameSession.query.filter_by(session_code=code).first_or_404()
    question_list = list(game_session.quiz.questions.order_by(Question.order_index).all())
    if not question_list:
        flash("This quiz has no questions.", "warning")
        return redirect(url_for("master.lobby", code=code))

    if game_session.state == "reveal":
        game_session.state = "leaderboard"
        db.session.commit()
        rankings = _leaderboard_payload(game_session)
        socketio.emit("leaderboard_updated", {"rankings": rankings}, room=code)
        return redirect(url_for("master.lobby", code=code))

    current_index = game_session.current_question_index
    if current_index + 1 >= len(question_list):
        game_session.state = "finished"
        game_session.ended_at = datetime.now(timezone.utc)
        db.session.commit()
        socketio.emit("session_finished", {"final_rankings": _leaderboard_payload(game_session)}, room=code)
        return redirect(url_for("master.lobby", code=code))

    game_session.current_question_index = current_index + 1
    game_session.state = "question"
    db.session.commit()
    _push_question(game_session)
    return redirect(url_for("master.lobby", code=code))


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
