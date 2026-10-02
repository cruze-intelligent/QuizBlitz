from flask import Blueprint, abort, redirect, render_template, request, session, url_for

from app.models import GameSession, Team, db

play_bp = Blueprint("play", __name__)


@play_bp.route("/<session_code>", methods=["GET"])
def join_form(session_code: str):
    session_record = GameSession.query.filter_by(session_code=session_code).first_or_404()
    return render_template("play/join.html", session_code=session_code, session=session_record, title="Join game")


@play_bp.route("/<session_code>/join", methods=["POST"])
def join_session(session_code: str):
    game_session = GameSession.query.filter_by(session_code=session_code).first_or_404()
    team_name = (request.form.get("team_name") or "").strip()
    if not team_name:
        return redirect(url_for("play.join_form", session_code=session_code))

    team = Team.query.filter_by(session_id=game_session.id, team_name=team_name).first()
    if team is None:
        team = Team(session_id=game_session.id, team_name=team_name, score=0)
        db.session.add(team)
        db.session.commit()

    session["team_id"] = team.id
    session["session_code"] = session_code
    return redirect(url_for("play.game", session_code=session_code))


@play_bp.route("/<session_code>/game", methods=["GET"])
def game(session_code: str):
    game_session = GameSession.query.filter_by(session_code=session_code).first_or_404()
    team_id = session.get("team_id")
    if not team_id:
        return redirect(url_for("play.join_form", session_code=session_code))

    team = db.session.get(Team, team_id)
    if not team or team.session_id != game_session.id:
        session.pop("team_id", None)
        session.pop("session_code", None)
        return redirect(url_for("play.join_form", session_code=session_code))

    return render_template("play/question.html", session_code=session_code, team_id=team_id, team=team, session=game_session, title="Game")
