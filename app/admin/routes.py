"""
app/admin/routes.py — Admin blueprint for quiz/user management.

All routes are protected by both @login_required and @admin_required.
The @admin_required decorator aborts with 403 if the user is not an admin.
"""

from functools import wraps

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.models import Quiz, QuizAttempt, QuizMaster, User, db
from app.quiz import editor

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
    if not QuizMaster.query.first():
        flash("Every quiz belongs to a quiz master. Create a quiz master account first.", "warning")
        return redirect(url_for("admin.dashboard"))

    form = editor.blank_form()
    if request.method == "POST":
        form, errors = _parse()
        if not errors:
            quiz = Quiz(created_by=form["owner_id"])
            editor.save(quiz, form)
            flash(f'Quiz "{quiz.title}" created successfully.', "success")
            return redirect(url_for("admin.dashboard"))

    return _render_form(form, "Create Quiz", url_for("admin.new_quiz"), is_new=True)


# ── Edit Quiz ──────────────────────────────────────────────────────────────

@admin_bp.route("/quiz/<int:quiz_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def edit_quiz(quiz_id: int):
    """Edit metadata and questions for an existing quiz."""
    quiz = db.session.get(Quiz, quiz_id)
    if not quiz:
        abort(404)

    game = editor.active_game(quiz)
    if game:
        flash(f"This quiz is being played now (game {game.session_code}). Edit it after the game ends.", "warning")
        return redirect(url_for("admin.dashboard"))

    form = editor.form_from_quiz(quiz)
    if request.method == "POST":
        form, errors = _parse()
        if not errors:
            quiz.created_by = form["owner_id"]
            editor.save(quiz, form)
            flash(f'Quiz "{quiz.title}" updated.', "success")
            return redirect(url_for("admin.dashboard"))

    return _render_form(form, "Edit Quiz", url_for("admin.edit_quiz", quiz_id=quiz_id), is_new=False)


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

def _parse():
    """Parse the form, requiring a quiz master as the owner.

    Admins are Users, whose ids overlap with QuizMaster ids, so an admin's own id must
    never be stored in Quiz.created_by.
    """
    form, errors = editor.parse_form(request.form)
    if form["owner_id"] is None or db.session.get(QuizMaster, form["owner_id"]) is None:
        errors.append("Choose the quiz master who owns this quiz.")
    for error in errors:
        flash(error, "danger")
    return form, errors


def _render_form(form: dict, title: str, action: str, is_new: bool):
    return render_template(
        "admin/quiz_form.html",
        form=form,
        is_new=is_new,
        masters=QuizMaster.query.order_by(QuizMaster.username).all(),
        title=title,
        action=action,
        back_url=url_for("admin.dashboard"),
    )
