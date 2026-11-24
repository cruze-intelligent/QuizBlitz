// Quiz master screens (lobby, question, reveal, leaderboard).
// State changes are server-rendered via POST + redirect; this script only adds the live
// bits: team roster/count, the "X / Y answered" meter, and the leaderboard animation.
document.addEventListener('DOMContentLoaded', () => {
  animateLeaderboard();

  startQuestionTimer();

  const root = document.querySelector('[data-session-code]');
  if (!root || typeof io === 'undefined') return;
  const room = root.dataset.sessionCode;

  const socket = io();
  // Re-join on every (re)connect so a dropped connection doesn't silently stop updates.
  socket.on('connect', () => socket.emit('join_room', { session_code: room }));

  const setText = (selector, value) => document.querySelectorAll(selector).forEach((el) => { el.textContent = value; });
  let totalTeams = Number(document.querySelector('[data-total-teams]')?.textContent || 0);

  socket.on('team_joined', (payload) => {
    setText('[data-team-count]', payload.team_count);
    totalTeams = payload.team_count;
    setText('[data-total-teams]', totalTeams);

    const list = document.querySelector('.lobby-layout .team-list');
    if (!list) return;
    list.querySelector('.team-list__empty')?.remove();
    // A team's phone re-emits join_room on reconnect; don't list it twice.
    if ([...list.children].some((li) => li.textContent === payload.team_name)) return;
    const item = document.createElement('li');
    item.textContent = payload.team_name;
    list.appendChild(item);
  });

  socket.on('answer_received', (payload) => {
    totalTeams = payload.total_teams;
    setText('[data-answers-in]', payload.answers_in);
    setText('[data-total-teams]', totalTeams);
    const bar = document.querySelector('[data-answer-bar]');
    if (bar) bar.style.width = `${totalTeams ? Math.round((payload.answers_in / totalTeams) * 100) : 0}%`;
  });
});

// Count down the open question, then reveal it automatically (the button works earlier).
// The extra wait lets answers sent in the last second arrive first.
function startQuestionTimer() {
  const bar = document.querySelector('[data-question-timer]');
  const form = document.querySelector('[data-reveal-form]');
  if (!bar || !form || bar.dataset.remainingMs === '') return;
  createCountdown(bar).start(Number(bar.dataset.remainingMs), Number(bar.dataset.totalSeconds), () => {
    setTimeout(() => form.requestSubmit(), 1500);
  });
}

// A page restored by the Back button would run an old timer; load the current screen instead.
window.addEventListener('pageshow', (event) => {
  if (event.persisted && document.querySelector('[data-question-timer]')) window.location.reload();
});

// FLIP: render rows in their new order, start each at its previous position, then let
// them slide into place so the room sees who overtook whom.
function animateLeaderboard() {
  const board = document.querySelector('[data-leaderboard]');
  if (!board || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  const rows = [...board.children];
  if (rows.length < 2) return;
  const step = rows[1].offsetTop - rows[0].offsetTop;

  let moved = false;
  rows.forEach((row) => {
    const offset = (Number(row.dataset.prevIndex) - Number(row.dataset.index)) * step;
    if (offset) {
      moved = true;
      row.style.transition = 'none';
      row.style.transform = `translateY(${offset}px)`;
      row.style.zIndex = offset > 0 ? '1' : '0'; // climbers slide over the rows they pass
    }
  });
  if (!moved) return;

  // Hold the old order briefly so viewers register it, then animate.
  setTimeout(() => {
    rows.forEach((row) => {
      row.style.transition = 'transform 0.9s cubic-bezier(0.2, 0.8, 0.2, 1)';
      row.style.transform = '';
    });
  }, 600);
}
