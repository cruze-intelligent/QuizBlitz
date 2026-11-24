"""
app/auth/routes.py — Authentication blueprint (register, login, logout).

All passwords are hashed by Werkzeug before storage.
CSRF is handled automatically by Flask-WTF on every form.
"""

from urllib.parse import urlsplit

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_limiter.util import get_remote_address
from flask_login import current_user, login_required, login_user, logout_user

from app import limiter
from app.auth.forms import LoginForm, RegistrationForm
from app.models import QuizMaster, User, db, find_account

auth_bp = Blueprint("auth", __name__)


def home_url() -> str:
    """Landing page for the current user: quiz masters run live games,
    admins manage content, regular users play self-paced quizzes."""
    if not current_user.is_authenticated:
        return url_for("auth.login")
    if isinstance(current_user._get_current_object(), QuizMaster):
        return url_for("master.dashboard")
    if current_user.is_admin:
        return url_for("admin.dashboard")
    return url_for("quiz.lobby")


def safe_next(target: str | None) -> str | None:
    """`target` if it is a path on this site, otherwise None.

    Browsers treat "//host" and "/\\host" as another site and drop control characters,
    so those are rejected as well as full URLs.
    """
    if not target or not target.startswith("/") or target.startswith("//"):
        return None
    if "\\" in target or not target.isprintable():
        return None
    parts = urlsplit(target)
    return None if parts.scheme or parts.netloc else target


def _login_key() -> str:
    return f"{get_remote_address()}:{request.form.get('email', '').strip().lower()[:120]}"


def _login_failed(response) -> bool:
    return response.status_code != 302


@auth_bp.route("/register", methods=["GET", "POST"])
@limiter.limit("20 per hour", methods=["POST"])
def register():
    """Create a new user account."""
    if current_user.is_authenticated:
        return redirect(home_url())

    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(
            username=form.username.data.strip(),
            email=form.email.data.strip().lower(),
        )
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()

        flash("Account created! You can now log in.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/register.html", form=form, title="Register")


# Only failed attempts count: 8 per account from one address, 40 from one address overall.
@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("8 per 15 minutes", key_func=_login_key, methods=["POST"], deduct_when=_login_failed)
@limiter.limit("40 per 15 minutes", methods=["POST"], deduct_when=_login_failed)
def login():
    """Log in with email and password."""
    if current_user.is_authenticated:
        return redirect(home_url())

    form = LoginForm()
    if form.validate_on_submit():
        user = find_account(form.email.data.strip().lower())
        if user and user.check_password(form.password.data):
            login_user(user, remember=form.remember_me.data)
            flash(f"Welcome back, {user.username}!", "success")
            return redirect(safe_next(request.args.get("next")) or home_url())

        flash("Invalid email or password.", "danger")

    return render_template("auth/login.html", form=form, title="Log In")


@auth_bp.route("/logout")
@login_required
def logout():
    """Clear the user session and redirect to login."""
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))
