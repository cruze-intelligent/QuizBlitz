"""SocketIO event handlers for live game sessions.

Team identity is never taken from the event payload. A team is created only by the
HTTP join flow (POST /play/<code>/join), which stores team_id + session_code in the
signed Flask session cookie. Flask-SocketIO exposes that cookie session to these
handlers (manage_session=True, the default), so the server knows which team a socket
belongs to; a client can't act as another team by sending a different team_id.
"""

from flask import session
from flask_socketio import emit, join_room
from sqlalchemy.exc import IntegrityError

from app import socketio
from app.models import GameSession, Option, Team, TeamAnswer, db


def _current_team(game_session: GameSession):
    """The team bound to this connection's cookie, if it belongs to `game_session`."""
    if session.get("session_code") != game_session.session_code:
        return None
    team_id = session.get("team_id")
    team = db.session.get(Team, team_id) if team_id else None
    if team is None or team.session_id != game_session.id:
        return None
    return team


@socketio.on("join_room")
def handle_join_room(data=None):
    """Subscribe to a session's room.

    Anyone with the code may listen (the master screen, spectators): room events carry
    no answer key before reveal. If this connection is a joined team, announce it.
    """
    payload = data if isinstance(data, dict) else {}
    session_code = payload.get("session_code")
    if not isinstance(session_code, str) or not session_code:
        return

    game_session = GameSession.query.filter_by(session_code=session_code).first()
    if not game_session:
        return

    join_room(session_code)

    team = _current_team(game_session)
    if team is not None:
        emit("team_joined", {"team_name": team.team_name, "team_count": game_session.team_count}, room=session_code)


@socketio.on("submit_answer")
def handle_submit_answer(data=None):
    payload = data if isinstance(data, dict) else {}
    session_code = payload.get("session_code")
    option_id = payload.get("option_id")
    if not isinstance(session_code, str) or not isinstance(option_id, int) or isinstance(option_id, bool):
        return

    game_session = GameSession.query.filter_by(session_code=session_code).first()
    if not game_session or game_session.state != "question":
        return

    team = _current_team(game_session)
    if team is None:
        return

    question = game_session.current_question()
    if question is None:
        return

    option = db.session.get(Option, option_id)
    if option is None or option.question_id != question.id:
        return

    # One answer per team per question. The DB unique constraint is the real guard;
    # catching IntegrityError covers two near-simultaneous taps that both pass a pre-check.
    answer = TeamAnswer(team_id=team.id, question_id=question.id, option_id=option.id, is_correct=bool(option.is_correct))
    db.session.add(answer)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return

    answers_in = TeamAnswer.query.filter_by(question_id=question.id).count()
    emit(
        "answer_received",
        {"answers_in": answers_in, "total_teams": game_session.team_count},
        room=session_code,
    )
