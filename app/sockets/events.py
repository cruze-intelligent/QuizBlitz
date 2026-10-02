from flask import request
from flask_socketio import emit, join_room

from app import socketio
from app.models import GameSession, Option, Team, TeamAnswer, db


@socketio.on("join_room")
def handle_join_room(data=None):
    payload = data or {}
    session_code = payload.get("session_code")
    team_name = (payload.get("team_name") or "").strip()
    if not session_code:
        return

    game_session = GameSession.query.filter_by(session_code=session_code).first()
    if not game_session:
        return

    join_room(session_code)

    if team_name:
        team = Team.query.filter_by(session_id=game_session.id, team_name=team_name).first()
        if team is None:
            team = Team(session_id=game_session.id, team_name=team_name, score=0)
            db.session.add(team)
            db.session.commit()
        emit("team_joined", {"team_name": team.team_name, "team_count": game_session.team_count}, room=session_code)


@socketio.on("submit_answer")
def handle_submit_answer(data=None):
    payload = data or {}
    session_code = payload.get("session_code")
    team_id = payload.get("team_id")
    option_id = payload.get("option_id")

    if not session_code or not team_id or not option_id:
        return

    game_session = GameSession.query.filter_by(session_code=session_code).first()
    team = db.session.get(Team, team_id)
    if not game_session or not team or team.session_id != game_session.id:
        return

    question = game_session.current_question()
    if question is None or game_session.state != "question":
        return

    if TeamAnswer.query.filter_by(team_id=team.id, question_id=question.id).count():
        return

    option = db.session.get(Option, option_id)
    if option is None or option.question_id != question.id:
        return

    answer = TeamAnswer(team_id=team.id, question_id=question.id, option_id=option.id, is_correct=bool(option.is_correct))
    db.session.add(answer)
    db.session.commit()

    answers_in = TeamAnswer.query.filter_by(question_id=question.id).count()
    emit(
        "answer_received",
        {"answers_in": answers_in, "total_teams": game_session.team_count},
        room=session_code,
    )
