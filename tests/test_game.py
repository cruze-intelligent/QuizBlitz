"""Live game: joining, resuming, timing, scoring and finishing."""

import time

from app import socketio
from app.models import GameSession, Option, Team, TeamAnswer, db
from conftest import PASSWORD, Game


def correct_option(app, code):
    with app.app_context():
        return GameSession.query.filter_by(session_code=code).one().current_question().correct_option.id


def wrong_option(app, code):
    with app.app_context():
        question = GameSession.query.filter_by(session_code=code).one().current_question()
        return question.options.filter(Option.is_correct.is_(False)).first().id


def test_full_game(app, game):
    alpha, beta = game.phone("Alpha").connect(), game.phone("Beta").connect()
    game.do("start")
    for number in range(15):
        events = alpha.events()
        assert events["question_pushed"]["question_num"] == number + 1
        assert "correct" not in str(events["question_pushed"])
        assert alpha.answer(correct_option(app, game.code)) == {"ok": True}
        assert beta.answer(wrong_option(app, game.code)) == {"ok": True}
        for step in ("reveal", "next", "next"):
            game.do(step)
    final = alpha.events()["session_finished"]["final_rankings"]
    assert [(row["team_name"], row["score"]) for row in final] == [("Alpha", 150), ("Beta", 0)]
    assert game.host.get(f"/master/session/{game.code}").status_code == 200


def test_team_name_cannot_be_taken_over(game):
    first = game.phone("Alpha")
    assert first.joined
    for name in ("Alpha", "alpha", "  ALPHA "):
        assert not game.phone(name).joined


def test_rejoining_phone_keeps_its_team(game):
    phone = game.phone("Alpha")
    again = phone.http.post(f"/play/{game.code}/join", data={"team_name": "Another"})
    assert again.headers["Location"].endswith("/game")
    with game.app.app_context():
        assert [team.team_name for team in Team.query] == ["Alpha"]


def test_team_name_rules(game):
    assert not game.phone("").joined
    assert not game.phone("x" * 41).joined
    assert game.phone("x" * 40).joined


def test_reconnect_restores_question_and_answer(app, game):
    phone = game.phone("Alpha").connect()
    game.do("start")
    state = phone.connect().events()["sync_state"]
    assert state["state"] == "question" and state["my_option_id"] is None
    assert 25_000 < state["question"]["remaining_ms"] <= 30_000
    assert "reveal" not in state and "correct" not in str(state)

    choice = wrong_option(app, game.code)
    phone.answer(choice)
    assert phone.connect().events()["sync_state"]["my_option_id"] == choice

    game.do("reveal")
    state = phone.connect().events()["sync_state"]
    assert state["reveal"]["correct_option_id"] == correct_option(app, game.code)

    game.do("next")
    assert phone.connect().events()["sync_state"]["rankings"][0]["team_name"] == "Alpha"


def host_screen(app, client, code):
    socket = socketio.test_client(app, flask_test_client=client)
    socket.emit("join_room", {"session_code": code})
    return socket


def test_live_counts_go_only_to_the_host(app, game, login):
    host = host_screen(app, game.host, game.code)
    rival = host_screen(app, login("rival"), game.code)
    alpha, beta = game.phone("Alpha").connect(), game.phone("Beta").connect()
    game.do("start")
    alpha.answer(wrong_option(app, game.code))

    received = [(event["name"], event["args"][0]) for event in host.get_received()]
    assert ("team_joined", {"team_name": "Beta", "team_count": 2}) in received
    assert ("answer_received", {"answers_in": 1, "total_teams": 2}) in received
    others = list(beta.events()) + [event["name"] for event in rival.get_received()]
    assert "question_pushed" in others
    assert not {"answer_received", "team_joined"} & set(others)


def test_one_answer_per_question(app, game):
    phone = game.phone("Alpha").connect()
    game.do("start")
    first = wrong_option(app, game.code)
    assert phone.answer(first)["ok"]
    assert phone.answer(correct_option(app, game.code)) == {"ok": False, "reason": "duplicate", "option_id": first}


def test_answers_after_the_deadline_are_refused(app, game):
    phone = game.phone("Alpha").connect()
    game.do("start")
    with app.app_context():
        session = GameSession.query.one()
        session.question_deadline = time.time() - 5
        db.session.commit()
    assert phone.answer(correct_option(app, game.code)) == {"ok": False, "reason": "closed"}


def test_waiting_in_line_does_not_make_an_answer_late(app, game, monkeypatch):
    from app.sockets import events

    phone = game.phone("Alpha").connect()
    game.do("start")
    with app.app_context():
        session = GameSession.query.one()
        session.question_deadline = time.time() + 1  # with the grace: answers count for 2 s
        db.session.commit()
    record = events._record_answer

    def after_a_queue(data, received_at):
        time.sleep(2.5)
        return record(data, received_at)

    monkeypatch.setattr(events, "_record_answer", after_a_queue)
    assert phone.answer(correct_option(app, game.code)) == {"ok": True}


def test_answers_after_reveal_are_refused(app, game):
    phone = game.phone("Alpha").connect()
    game.do("start")
    game.do("reveal")
    assert phone.answer(correct_option(app, game.code))["reason"] == "closed"


def test_reveal_scores_once(app, game):
    phone = game.phone("Alpha").connect()
    game.do("start")
    phone.answer(correct_option(app, game.code))
    game.do("reveal")
    game.do("reveal")
    with app.app_context():
        assert Team.query.one().score == 10


def test_strangers_cannot_answer(app, game):
    game.do("start")
    stranger = game.phone("")  # rejected, so no team cookie
    stranger.connect()
    assert stranger.answer(correct_option(app, game.code))["reason"] == "not_joined"
    with app.app_context():
        assert TeamAnswer.query.count() == 0


def test_finished_game_cannot_be_joined(game):
    phone = game.phone("Alpha").connect()
    game.do("end")
    assert "session_finished" in phone.events()
    late = game.phone("Late")
    assert late.join_response.status_code == 410
    assert late.http.get(f"/play/{game.code}").status_code == 410
    # A team from that game still sees the final results.
    assert phone.connect().events()["sync_state"]["state"] == "finished"


def test_game_full(make_app):
    app = make_app(MAX_TEAMS_PER_SESSION=1)
    host = app.test_client()
    host.post("/auth/login", data={"email": "host@example.com", "password": PASSWORD})
    game = Game(app, host, 1)
    assert game.phone("One").joined
    assert not game.phone("Two").joined


def test_join_code_ignores_case(game):
    assert game.app.test_client().get(f"/play/{game.code.lower()}").status_code == 200


def test_other_quiz_masters_cannot_control_a_game(game, login):
    rival = login("rival")
    for step in ("start", "reveal", "next", "end"):
        assert rival.post(f"/master/session/{game.code}/{step}").status_code == 404
    assert rival.get(f"/master/session/{game.code}/lobby").status_code == 404


def test_master_pages_render(game):
    for path in ("/master/", "/master/quiz/new", "/master/quiz/1/edit", f"/master/session/{game.code}/lobby"):
        assert game.host.get(path).status_code == 200
    assert game.code in game.host.get("/master/").text
    game.do("start")
    assert "data-remaining-ms" in game.host.get(f"/master/session/{game.code}").text
