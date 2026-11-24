// Team phone: shows the current screen and submits answers over Socket.IO.
//
// Live events carry each step of the game. On every (re)connect the server also sends
// "sync_state" with the whole current screen, so a refresh or dropped connection resumes
// where the game is. Each message has a sequence number; older ones are ignored.
document.addEventListener('DOMContentLoaded', () => {
  const root = document.querySelector('[data-session-code]');
  if (!root) return;
  const sessionCode = root.dataset.sessionCode;
  const teamName = root.dataset.teamName;
  // No team id/name is sent: the server identifies the team from the session cookie.

  const questionLabel = document.getElementById('question-label');
  const questionText = document.getElementById('question-text');
  const optionList = document.getElementById('option-list');
  const rankList = document.getElementById('rank-list');
  const status = document.getElementById('status-message');
  const countdown = createCountdown(document.getElementById('live-timer'));

  if (typeof io === 'undefined') {
    status.textContent = "Couldn't load the game. Check your connection and refresh the page.";
    return;
  }

  let lastSeq = -Infinity;
  const isStale = (payload) => {
    if (payload.seq < lastSeq) return true;
    lastSeq = payload.seq;
    return false;
  };

  const buttons = () => [...optionList.querySelectorAll('.answer-option')];
  const lockOptions = () => buttons().forEach((button) => { button.disabled = true; });

  function showWaiting() {
    countdown.stop();
    questionLabel.hidden = true;
    questionText.textContent = "You're in!";
    optionList.replaceChildren();
    rankList.hidden = true;
    status.textContent = 'Waiting for the game to start.';
  }

  function showQuestion(payload, selectedId = null) {
    questionLabel.hidden = false;
    questionLabel.textContent = `Round ${payload.round} · Question ${payload.question_num} of ${payload.total_questions}`;
    questionText.textContent = payload.question_text;
    rankList.hidden = true;
    status.textContent = '';
    optionList.replaceChildren(...payload.options.map((option) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'answer-option';
      button.dataset.optionId = option.id; // read back on reveal to highlight the correct option
      button.textContent = option.text;
      button.addEventListener('click', () => submit(button, option.id));
      return button;
    }));

    if (selectedId !== null) {
      markSelected(selectedId);
      lockOptions();
      status.textContent = 'Answer submitted!';
    }
    countdown.start(payload.remaining_ms, payload.time_limit_seconds, () => {
      lockOptions();
      if (!optionList.querySelector('.is-selected')) status.textContent = "Time's up!";
    });
  }

  function markSelected(optionId) {
    buttons().forEach((button) => button.classList.toggle('is-selected', Number(button.dataset.optionId) === optionId));
  }

  function submit(button, optionId) {
    markSelected(optionId);
    lockOptions();
    status.textContent = 'Sending…';
    const seqAtSubmit = lastSeq;

    socket.emit('submit_answer', { session_code: sessionCode, option_id: optionId }, (reply) => {
      if (lastSeq !== seqAtSubmit) return; // the game moved on while this was in flight
      if (reply && (reply.ok || reply.reason === 'duplicate')) {
        // Lock again: a reconnect may have redrawn the options while this was in flight.
        markSelected(reply.ok ? optionId : reply.option_id);
        lockOptions();
        status.textContent = 'Answer submitted!';
      } else {
        markSelected(null);
        status.textContent = reply && reply.reason === 'closed'
          ? "Time's up! That answer arrived too late."
          : "That answer wasn't accepted. Refresh the page.";
      }
    });
  }

  function showReveal(payload) {
    countdown.stop();
    const selected = optionList.querySelector('.is-selected');
    lockOptions();
    buttons().forEach((button) => {
      if (Number(button.dataset.optionId) === payload.correct_option_id) button.classList.add('is-correct');
      else if (button === selected) button.classList.add('is-wrong'); // team's own wrong pick
    });
    const mine = payload.team_results.find((result) => result.team_name === teamName);
    const verdict = mine && mine.is_correct ? 'Correct!' : mine && mine.answered ? 'Not this time.' : 'No answer.';
    status.textContent = `${verdict} Answer: ${payload.correct_option_text} (${payload.passed_count} correct, ${payload.failed_count} wrong or no answer)`;
  }

  function showRankings(rankings, isFinal) {
    countdown.stop();
    questionLabel.hidden = true;
    optionList.replaceChildren();
    questionText.textContent = isFinal ? 'Final results' : 'Leaderboard';
    rankList.hidden = false;
    rankList.replaceChildren(...rankings.map(rankRow));

    const mine = rankings.find((row) => row.team_name === teamName);
    const place = mine ? `You're #${mine.rank} with ${mine.score} points. ` : '';
    status.textContent = place + (isFinal ? 'Thanks for playing!' : 'Next question coming up.');
  }

  function rankRow(row) {
    const item = document.createElement('li');
    item.className = 'rank-row';
    if (row.rank <= 3) item.classList.add(`rank-row--top${row.rank}`);
    if (row.team_name === teamName) item.classList.add('rank-row--mine');
    const cell = (className, value) => {
      const span = document.createElement('span');
      span.className = className;
      span.textContent = value;
      return span;
    };
    item.append(
      cell('rank-row__rank', row.rank),
      cell('rank-row__name', row.team_name),
      cell(row.score_delta ? 'delta-badge' : '', row.score_delta ? `+${row.score_delta}` : ''),
      cell('rank-row__score', row.score),
    );
    return item;
  }

  const socket = io();
  socket.on('connect', () => socket.emit('join_room', { session_code: sessionCode }));
  socket.on('disconnect', () => { status.textContent = 'Connection lost. Reconnecting…'; });

  socket.on('sync_state', (payload) => {
    if (isStale(payload)) return;
    if (payload.state === 'lobby') showWaiting();
    else if (payload.state === 'question') showQuestion(payload.question, payload.my_option_id);
    else if (payload.state === 'reveal') {
      showQuestion(payload.question, payload.my_option_id);
      showReveal(payload.reveal);
    } else showRankings(payload.rankings, payload.state === 'finished');
  });

  socket.on('question_pushed', (payload) => { if (!isStale(payload)) showQuestion(payload); });
  socket.on('answer_revealed', (payload) => { if (!isStale(payload)) showReveal(payload); });
  socket.on('leaderboard_updated', (payload) => { if (!isStale(payload)) showRankings(payload.rankings, false); });
  socket.on('session_finished', (payload) => { if (!isStale(payload)) showRankings(payload.final_rankings, true); });
});
