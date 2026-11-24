from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from app import limiter
from app.models import GameSession, Team, db

play_bp = Blueprint("play", __name__)

MAX_TEAM_NAME = 40


def _game_session(session_code: str) -> GameSession:
    return GameSession.query.filter_by(session_code=session_code.upper()).first_or_404()


def _joined_team(game_session: GameSession):
    """The team this browser has already joined in this game, or None."""
    if session.get("session_code") != game_session.session_code:
        return None
    team = db.session.get(Team, session.get("team_id") or 0)
    return team if team and team.session_id == game_session.id else None


@play_bp.route("/<session_code>", methods=["GET"])
def join_form(session_code: str):
    game_session = _game_session(session_code)
    if _joined_team(game_session):
        return redirect(url_for("play.game", session_code=game_session.session_code))
    if game_session.state == "finished":
        return _finished()
    return render_template("play/join.html", session_code=game_session.session_code, title="Join game")


# A whole venue usually shares one public IP address, so this has to be generous.
@play_bp.route("/<session_code>/join", methods=["POST"])
@limiter.limit("200 per minute")
def join_session(session_code: str):
    game_session = _game_session(session_code)
    code = game_session.session_code
    if _joined_team(game_session):
        return redirect(url_for("play.game", session_code=code))
    if game_session.state == "finished":
        return _finished()

    team_name = " ".join((request.form.get("team_name") or "").split())
    error = None
    if not team_name:
        error = "Enter a team name."
    elif len(team_name) > MAX_TEAM_NAME or not team_name.isprintable():
        error = f"Use a team name of at most {MAX_TEAM_NAME} characters."
    elif game_session.team_count >= current_app.config["MAX_TEAMS_PER_SESSION"]:
        error = "This game is full."
    # Never hand out an existing team: anyone could take over a rival by typing its name.
    elif game_session.teams.filter(func.lower(Team.team_name) == func.lower(team_name)).first():
        error = "That team name is taken. Choose another."
    if error:
        return _join_error(code, error)

    team = Team(session_id=game_session.id, team_name=team_name, score=0)
    db.session.add(team)
    try:
        db.session.commit()
    except IntegrityError:
        # Another phone claimed the name at the same moment.
        db.session.rollback()
        return _join_error(code, "That team name is taken. Choose another.")

    session.permanent = True
    session["team_id"] = team.id
    session["session_code"] = code
    return redirect(url_for("play.game", session_code=code))


@play_bp.route("/<session_code>/game", methods=["GET"])
def game(session_code: str):
    game_session = _game_session(session_code)
    team = _joined_team(game_session)
    if team is None:
        return redirect(url_for("play.join_form", session_code=game_session.session_code))
    return render_template(
        "play/question.html", session_code=game_session.session_code, team=team, title="Game"
    )


def _join_error(session_code: str, message: str):
    flash(message, "danger")
    return redirect(url_for("play.join_form", session_code=session_code))


def _finished():
    return (
        render_template(
            "error.html",
            title="This game has finished",
            message="Ask your quiz master for the code of the next game.",
        ),
        410,
    )
