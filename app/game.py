"""Live-game data shared by the quiz master's screens and the Socket.IO events.

Nothing here puts the answer key in a payload unless the session has reached REVEAL.
"""

from collections import Counter

from app.models import GameSession, Option, Question, Team, TeamAnswer

_STATE_ORDER = {"question": 0, "reveal": 1, "leaderboard": 2, "finished": 3}


def sequence(game_session: GameSession) -> int:
    """Increases with every step of a game, so a phone can ignore messages that arrive late."""
    if game_session.state == "lobby":
        return -1
    if game_session.state == "finished":
        return 1_000_000
    return game_session.current_question_index * 4 + _STATE_ORDER[game_session.state]


def question_payload(game_session: GameSession, question: Question) -> dict:
    """The open question as sent to phones (no answer key)."""
    options = question.options.order_by(Option.order_index).all()
    return {
        "seq": sequence(game_session),
        "question_text": question.text,
        "options": [{"id": option.id, "text": option.text} for option in options],
        "round": question.round_number,
        "question_num": game_session.current_question_index + 1,
        "total_questions": game_session.quiz.question_count,
        "time_limit_seconds": question.time_limit_seconds,
        # Time left rather than an end time: phone clocks are often wrong.
        "remaining_ms": game_session.remaining_ms(),
    }


def reveal_summary(game_session: GameSession, question: Question) -> dict:
    """Results for a revealed question: correct option, per-option pick counts and
    each team's outcome. Teams that didn't answer count as failed (spec)."""
    correct = question.correct_option
    answers = {answer.team_id: answer for answer in game_session.answers_for(question).all()}
    picks = Counter(answer.option_id for answer in answers.values())

    team_results = []
    for team in game_session.teams.order_by(Team.joined_at.asc()).all():
        answer = answers.get(team.id)
        team_results.append({
            "team_name": team.team_name,
            "is_correct": bool(answer and answer.is_correct),
            "answered": answer is not None,
        })
    passed = sum(result["is_correct"] for result in team_results)

    return {
        "correct_option_id": correct.id if correct else None,
        "correct_option_text": correct.text if correct else "",
        "passed_count": passed,
        "failed_count": len(team_results) - passed,
        "team_results": team_results,
        "options": [
            {"id": option.id, "text": option.text, "is_correct": option.is_correct, "count": picks.get(option.id, 0)}
            for option in question.options.order_by(Option.order_index).all()
        ],
    }


def reveal_payload(game_session: GameSession, question: Question) -> dict:
    """Reveal results in the socket payload shape from the spec."""
    summary = reveal_summary(game_session, question)
    keys = ("correct_option_id", "correct_option_text", "passed_count", "failed_count", "team_results")
    return {"seq": sequence(game_session), **{key: summary[key] for key in keys}}


def rankings(game_session: GameSession) -> list[dict]:
    """Leaderboard rows, best first.

    - rank: standard competition ranking, so tied scores share a rank (1, 1, 3).
    - score_delta: points gained on the most recently revealed question.
    - prev_index / movement: position and rank change versus the standings before that
      question, used to animate rows into their new order. There are no previous
      standings before the first question, so nothing moves then.
    """
    teams = game_session.teams.order_by(Team.joined_at.asc()).all()
    question = game_session.current_question()
    gained = {}
    if question is not None and game_session.state in ("reveal", "leaderboard", "finished"):
        correct_answers = game_session.answers_for(question).filter(TeamAnswer.is_correct.is_(True))
        gained = {answer.team_id: question.points for answer in correct_answers}
    has_previous = game_session.current_question_index > 0

    rows = []
    for team in teams:
        delta = gained.get(team.id, 0)
        rows.append({"team_name": team.team_name, "score": team.score, "delta": delta, "prev_score": team.score - delta})
    # sorted() is stable, so equal scores keep join order (then previous position).
    for index, row in enumerate(sorted(rows, key=lambda r: -r["prev_score"])):
        row["prev_index"] = index
    ordered = sorted(rows, key=lambda r: (-r["score"], r["prev_index"]))

    scores = [row["score"] for row in rows]
    prev_scores = [row["prev_score"] for row in rows]
    result = []
    for index, row in enumerate(ordered):
        rank = 1 + sum(score > row["score"] for score in scores)
        prev_rank = 1 + sum(score > row["prev_score"] for score in prev_scores)
        result.append({
            "rank": rank,
            "team_name": row["team_name"],
            "score": row["score"],
            "score_delta": row["delta"],
            "prev_index": row["prev_index"] if has_previous else index,
            "movement": (prev_rank - rank) if has_previous else 0,
        })
    return result


def public_rankings(game_session: GameSession) -> list[dict]:
    """Rankings in the socket payload shape from the spec."""
    keys = ("rank", "team_name", "score", "score_delta")
    return [{key: row[key] for key in keys} for row in rankings(game_session)]


def sync_payload(game_session: GameSession, team: Team | None) -> dict:
    """Everything a phone needs to show the current screen after a refresh or reconnect."""
    payload = {"state": game_session.state, "seq": sequence(game_session)}
    question = game_session.current_question()

    if game_session.state in ("question", "reveal") and question is not None:
        payload["question"] = question_payload(game_session, question)
        answer = game_session.answers_for(question).filter(TeamAnswer.team_id == team.id).first() if team else None
        payload["my_option_id"] = answer.option_id if answer else None
    if game_session.state == "reveal" and question is not None:
        payload["reveal"] = reveal_payload(game_session, question)
    if game_session.state in ("leaderboard", "finished"):
        payload["rankings"] = public_rankings(game_session)
    return payload
