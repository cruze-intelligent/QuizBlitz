"""
app/quiz/routes.py — Quiz blueprint: lobby, play, submit, results, leaderboard.

Security notes:
  - All routes require @login_required.
  - Scoring is performed server-side in utils.calculate_score().
  - The answer key is NEVER sent to the browser.
  - Quiz start time is stored in the Flask session (server-side cookie).
"""

import json
from datetime import datetime, timezone

from flask import (
    Blueprint, render_template, redirect, url_for,
    flash, request, session, abort
)
from flask_login import login_required, current_user
from sqlalchemy import func

from app.models import db, Quiz, Question, Option, QuizAttempt
from app.quiz.utils import calculate_score, format_time

quiz_bp = Blueprint("quiz", __name__)


# ── Lobby ──────────────────────────────────────────────────────────────────

@quiz_bp.route("/")
@login_required
def lobby():
    """
    Show all published quizzes with optional category / difficulty filters.
    """
    category = request.args.get("category", "").strip()
    difficulty = request.args.get("difficulty", "").strip()

    query = Quiz.query.filter_by(is_published=True)

    if category:
        query = query.filter(func.lower(Quiz.category) == category.lower())
    if difficulty:
        query = query.filter_by(difficulty=difficulty)

    quizzes = query.order_by(Quiz.created_at.desc()).all()

    # Build list of distinct categories for the filter UI
    categories = [
        r[0] for r in db.session.query(Quiz.category)
        .filter_by(is_published=True)
        .distinct()
        .order_by(Quiz.category)
    ]

    return render_template(
        "quiz/lobby.html",
        quizzes=quizzes,
        categories=categories,
        selected_category=category,
        selected_difficulty=difficulty,
        title="Quiz Lobby",
    )


# ── Start ──────────────────────────────────────────────────────────────────

@quiz_bp.route("/<int:quiz_id>/start")
@login_required
def start(quiz_id: int):
    """
    Record quiz start time in the session, then redirect to the play view.
    Storing start time server-side prevents client clock manipulation.
    """
    quiz = Quiz.query.filter_by(id=quiz_id, is_published=True).first_or_404()

    # Stamp the start time in the server session
    session[f"quiz_{quiz_id}_start"] = datetime.now(timezone.utc).isoformat()

    return redirect(url_for("quiz.play", quiz_id=quiz_id))


# ── Play ───────────────────────────────────────────────────────────────────

@quiz_bp.route("/<int:quiz_id>/play")
@login_required
def play(quiz_id: int):
    """
    Render the single-page quiz player.

    Questions are passed to the template as plain dicts (no is_correct flag)
    so the answer key is never present in the HTML source.
    """
    quiz = Quiz.query.filter_by(id=quiz_id, is_published=True).first_or_404()

    # Ensure start was recorded; if not, restart the timer gracefully
    if f"quiz_{quiz_id}_start" not in session:
        session[f"quiz_{quiz_id}_start"] = datetime.now(timezone.utc).isoformat()

    # Build a sanitised question list — NO is_correct field exposed
    questions_data = []
    for q in quiz.questions:
        questions_data.append({
            "id": q.id,
            "text": q.text,
            "options": [
                {"id": opt.id, "text": opt.text}
                for opt in q.options
            ],
        })

    return render_template(
        "quiz/play.html",
        quiz=quiz,
        questions_json=json.dumps(questions_data),
        title=quiz.title,
    )


# ── Submit ─────────────────────────────────────────────────────────────────

@quiz_bp.route("/<int:quiz_id>/submit", methods=["POST"])
@login_required
def submit(quiz_id: int):
    """
    Receive the raw answer selections from the client, score them
    server-side, persist a QuizAttempt, then redirect to results.

    The client POSTs a hidden field `answers` containing a JSON object
    of the form:  {"question_id": "option_id", ...}
    """
    quiz = Quiz.query.filter_by(id=quiz_id, is_published=True).first_or_404()

    # Parse answers from hidden form field
    raw = request.form.get("answers", "{}")
    try:
        answers = json.loads(raw)
    except (ValueError, TypeError):
        answers = {}

    # ── Server-side scoring ------------------------------------------------
    earned, total = calculate_score(quiz_id, answers)

    # ── Calculate time taken ───────────────────────────────────────────────
    start_key = f"quiz_{quiz_id}_start"
    time_taken = quiz.time_limit_seconds   # fallback: full time used

    if start_key in session:
        start_iso = session.pop(start_key)
        try:
            start_dt = datetime.fromisoformat(start_iso)
            delta = datetime.now(timezone.utc) - start_dt
            time_taken = min(int(delta.total_seconds()), quiz.time_limit_seconds)
        except (ValueError, TypeError):
            pass

    # ── Persist attempt ────────────────────────────────────────────────────
    attempt = QuizAttempt(
        user_id=current_user.id,
        quiz_id=quiz_id,
        score=earned,
        total_points=total,
        time_taken_seconds=time_taken,
    )
    db.session.add(attempt)
    db.session.commit()

    return redirect(url_for("quiz.results", quiz_id=quiz_id, attempt_id=attempt.id))


# ── Results ────────────────────────────────────────────────────────────────

@quiz_bp.route("/<int:quiz_id>/results")
@login_required
def results(quiz_id: int):
    """Show the score, correct answers, and time taken for a completed attempt."""
    quiz = Quiz.query.filter_by(id=quiz_id, is_published=True).first_or_404()

    attempt_id = request.args.get("attempt_id", type=int)
    attempt = db.session.get(QuizAttempt, attempt_id)

    # Guard: only the attempt owner may view this page
    if not attempt or attempt.user_id != current_user.id or attempt.quiz_id != quiz_id:
        abort(404)

    # Build question + correct-answer data for the review section
    review = []
    for q in quiz.questions:
        correct_opt = q.correct_option
        review.append({
            "question": q,
            "correct_option": correct_opt,
        })

    return render_template(
        "quiz/results.html",
        quiz=quiz,
        attempt=attempt,
        review=review,
        format_time=format_time,
        title="Your Results",
    )


# ── Leaderboard ────────────────────────────────────────────────────────────

@quiz_bp.route("/<int:quiz_id>/leaderboard")
@login_required
def leaderboard(quiz_id: int):
    """Show the top 10 attempts for this quiz, ordered by score then time."""
    quiz = Quiz.query.filter_by(id=quiz_id, is_published=True).first_or_404()

    top_attempts = (
        QuizAttempt.query
        .filter_by(quiz_id=quiz_id)
        .order_by(QuizAttempt.score.desc(), QuizAttempt.time_taken_seconds.asc())
        .limit(10)
        .all()
    )

    return render_template(
        "quiz/leaderboard.html",
        quiz=quiz,
        attempts=top_attempts,
        format_time=format_time,
        title=f"Leaderboard — {quiz.title}",
    )
