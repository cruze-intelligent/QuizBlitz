"""
app/admin/routes.py — Admin blueprint for quiz/user management.

All routes are protected by both @login_required and @admin_required.
The @admin_required decorator aborts with 403 if the user is not an admin.
"""

from functools import wraps
from flask import (
    Blueprint, render_template, redirect, url_for,
    flash, request, abort
)
from flask_login import login_required, current_user

from app.models import db, Quiz, Question, Option, User, QuizAttempt

admin_bp = Blueprint("admin", __name__)


# ── Admin guard decorator ──────────────────────────────────────────────────

def admin_required(f):
    """
    Decorator that restricts a route to admin users only.
    Must be applied AFTER @login_required.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated


# ── Dashboard ──────────────────────────────────────────────────────────────

@admin_bp.route("/")
@login_required
@admin_required
def dashboard():
    """Admin overview: list of all quizzes, user count, attempt stats."""
    quizzes = Quiz.query.order_by(Quiz.created_at.desc()).all()
    user_count = User.query.count()
    attempt_count = QuizAttempt.query.count()

    return render_template(
        "admin/dashboard.html",
        quizzes=quizzes,
        user_count=user_count,
        attempt_count=attempt_count,
        title="Admin Dashboard",
    )


# ── Create Quiz ────────────────────────────────────────────────────────────

@admin_bp.route("/quiz/new", methods=["GET", "POST"])
@login_required
@admin_required
def new_quiz():
    """Render and handle the create-quiz form."""
    if request.method == "POST":
        quiz = _quiz_from_form(request.form, creator_id=current_user.id)
        db.session.add(quiz)
        db.session.flush()   # get quiz.id before adding questions

        _save_questions(quiz.id, request.form)
        db.session.commit()

        flash(f'Quiz "{quiz.title}" created successfully.', "success")
        return redirect(url_for("admin.dashboard"))

    return render_template(
        "admin/quiz_form.html",
        quiz=None,
        title="Create Quiz",
        action=url_for("admin.new_quiz"),
    )


# ── Edit Quiz ──────────────────────────────────────────────────────────────

@admin_bp.route("/quiz/<int:quiz_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def edit_quiz(quiz_id: int):
    """Edit metadata and questions for an existing quiz."""
    quiz = db.session.get(Quiz, quiz_id)
    if not quiz:
        abort(404)

    if request.method == "POST":
        # Update scalar fields
        quiz.title = request.form.get("title", "").strip()
        quiz.description = request.form.get("description", "").strip()
        quiz.category = request.form.get("category", "General").strip()
        quiz.difficulty = request.form.get("difficulty", "easy")
        quiz.time_limit_seconds = int(request.form.get("time_limit_seconds", 180))
        quiz.is_published = "is_published" in request.form

        # Replace all questions with what was submitted
        for q in quiz.questions.all():
            db.session.delete(q)
        db.session.flush()

        _save_questions(quiz.id, request.form)
        db.session.commit()

        flash(f'Quiz "{quiz.title}" updated.', "success")
        return redirect(url_for("admin.dashboard"))

    return render_template(
        "admin/quiz_form.html",
        quiz=quiz,
        title="Edit Quiz",
        action=url_for("admin.edit_quiz", quiz_id=quiz_id),
    )


# ── Delete (soft) Quiz ─────────────────────────────────────────────────────

@admin_bp.route("/quiz/<int:quiz_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_quiz(quiz_id: int):
    """Soft-delete: set is_published=False so the quiz disappears from the lobby."""
    quiz = db.session.get(Quiz, quiz_id)
    if not quiz:
        abort(404)

    quiz.is_published = False
    db.session.commit()
    flash(f'Quiz "{quiz.title}" has been unpublished.', "info")
    return redirect(url_for("admin.dashboard"))


# ── Helpers ────────────────────────────────────────────────────────────────

def _quiz_from_form(form_data, creator_id: int) -> Quiz:
    """Build a Quiz object from POST form data."""
    return Quiz(
        title=form_data.get("title", "").strip(),
        description=form_data.get("description", "").strip(),
        category=form_data.get("category", "General").strip(),
        difficulty=form_data.get("difficulty", "easy"),
        time_limit_seconds=int(form_data.get("time_limit_seconds", 180)),
        is_published="is_published" in form_data,
        created_by=creator_id,
    )


def _save_questions(quiz_id: int, form_data) -> None:
    """
    Parse question + option data from a multi-value form submission and
    persist Question / Option rows.

    Expected form field pattern:
      question_text_0, question_text_1, …
      option_text_0_0, option_text_0_1, option_text_0_2, option_text_0_3
      correct_option_0  (value = "0" | "1" | "2" | "3")
    """
    idx = 0
    while True:
        q_text = form_data.get(f"question_text_{idx}", "").strip()
        if not q_text:
            break

        question = Question(
            quiz_id=quiz_id,
            text=q_text,
            order_index=idx,
            points=1,
        )
        db.session.add(question)
        db.session.flush()

        correct_idx = int(form_data.get(f"correct_option_{idx}", 0))

        for opt_idx in range(4):
            opt_text = form_data.get(f"option_text_{idx}_{opt_idx}", "").strip()
            if not opt_text:
                continue
            option = Option(
                question_id=question.id,
                text=opt_text,
                is_correct=(opt_idx == correct_idx),
                order_index=opt_idx,
            )
            db.session.add(option)

        idx += 1
