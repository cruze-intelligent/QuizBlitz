"""SocketIO event handlers for live game sessions.

Team identity is never taken from the event payload. A team is created only by the
HTTP join flow (POST /play/<code>/join), which stores team_id + session_code in the
signed Flask session cookie. Flask-SocketIO exposes that cookie session to these
handlers (manage_session=True, the default), so the server knows which team a socket
belongs to; a client can't act as another team by sending a different team_id.
"""

import threading
import time

from flask import session
from flask_login import current_user
from flask_socketio import emit, join_room
from sqlalchemy.exc import IntegrityError

from app import socketio
from app.game import sync_payload
from app.models import GameSession, Option, QuizMaster, Team, TeamAnswer, db


# Answers are recorded one at a time. Each takes a few milliseconds, but when a whole room
# taps at once, that many threads competing for the interpreter are several times slower
# than taking turns. One lock is enough because the app runs as a single process.
_answer_lock = threading.Lock()


def _current_team(game_session: GameSession):
    """The team bound to this connection's cookie, if it belongs to `game_session`."""
    if session.get("session_code") != game_session.session_code:
        return None
    team_id = session.get("team_id")
    team = db.session.get(Team, team_id) if team_id else None
    if team is None or team.session_id != game_session.id:
        return None
    return team


def _host_room(session_code: str) -> str:
    """Room for the quiz master's own screens.

    Live counts go only here. Sent to every phone, N answers would mean N x N messages,
    which delays the answers still waiting when a whole room taps at once.
    """
    return f"{session_code}:host"


def _is_host(game_session: GameSession) -> bool:
    user = current_user._get_current_object()
    return isinstance(user, QuizMaster) and game_session.quiz.created_by == user.id


@socketio.on("join_room")
def handle_join_room(data=None):
    """Subscribe to a session's room and send this client the current screen.

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

    # Join before reading the state: anything that changes in between reaches this client
    # as an event, and the sequence number tells it which message is newer.
    join_room(session_code)
    if _is_host(game_session):
        join_room(_host_room(session_code))
    db.session.refresh(game_session)

    team = _current_team(game_session)
    emit("sync_state", sync_payload(game_session, team))
    if team is not None and game_session.state != "finished":
        emit("team_joined", {"team_name": team.team_name, "team_count": game_session.team_count}, room=_host_room(session_code))


@socketio.on("submit_answer")
def handle_submit_answer(data=None):
    """Record a team's answer. The return value is the acknowledgement the phone shows."""
    received_at = time.time()
    with _answer_lock:
        return _record_answer(data, received_at)


def _record_answer(data, received_at: float) -> dict:
    payload = data if isinstance(data, dict) else {}
    session_code = payload.get("session_code")
    option_id = payload.get("option_id")
    if not isinstance(session_code, str) or not isinstance(option_id, int) or isinstance(option_id, bool):
        return {"ok": False, "reason": "invalid"}

    game_session = GameSession.query.filter_by(session_code=session_code).first()
    team = _current_team(game_session) if game_session else None
    if team is None:
        return {"ok": False, "reason": "not_joined"}
    # Judged by arrival time, so waiting for the lock can't make an answer late.
    if not game_session.accepts_answers(received_at):
        return {"ok": False, "reason": "closed"}

    question = game_session.current_question()
    option = db.session.get(Option, option_id)
    if question is None or option is None or option.question_id != question.id:
        return {"ok": False, "reason": "invalid"}

    # is_correct stays False until the reveal scores it: an answer that slips in while the
    # reveal is running can then never be shown as correct without its points.
    team_id, question_id = team.id, question.id
    db.session.add(TeamAnswer(team_id=team_id, question_id=question_id, option_id=option.id))

    # One answer per team per question. The DB unique constraint is the real guard, and
    # also covers two near-simultaneous taps.
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        existing = TeamAnswer.query.filter_by(team_id=team_id, question_id=question_id).first()
        return {"ok": False, "reason": "duplicate", "option_id": existing.option_id if existing else None}

    answers_in = game_session.answers_for(question).count()
    emit(
        "answer_received",
        {"answers_in": answers_in, "total_teams": game_session.team_count},
        room=_host_room(session_code),
    )
    return {"ok": True}
