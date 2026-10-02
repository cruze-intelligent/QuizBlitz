"""
app/auth/routes.py — Authentication blueprint (register, login, logout).

All passwords are hashed by Werkzeug before storage.
CSRF is handled automatically by Flask-WTF on every form.
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user

from app.models import db, QuizMaster, User
from app.auth.forms import RegistrationForm, LoginForm

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    """Create a new user account."""
    if current_user.is_authenticated:
        return redirect(url_for("quiz.lobby"))

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


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """Log in with email and password."""
    if current_user.is_authenticated:
        return redirect(url_for("master.dashboard"))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.strip().lower()).first()
        if user is None:
            user = QuizMaster.query.filter_by(email=form.email.data.strip().lower()).first()

        if user and user.check_password(form.password.data):
            login_user(user, remember=form.remember_me.data)
            next_page = request.args.get("next")
            flash(f"Welcome back, {user.username}!", "success")
            return redirect(next_page or url_for("master.dashboard"))

        flash("Invalid email or password.", "danger")

    return render_template("auth/login.html", form=form, title="Log In")


@auth_bp.route("/logout")
@login_required
def logout():
    """Clear the user session and redirect to login."""
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))
