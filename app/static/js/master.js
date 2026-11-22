// Quiz master lobby: live team roster + answer counter over Socket.IO.
document.addEventListener('DOMContentLoaded', () => {
  const root = document.querySelector('[data-session-code]');
  if (!root || typeof io === 'undefined') return;
  const room = root.dataset.sessionCode;

  const socket = io();
  // Re-join on every (re)connect so a dropped connection doesn't silently stop updates.
  socket.on('connect', () => socket.emit('join_room', { session_code: room }));

  const list = document.querySelector('.team-list');
  const count = document.querySelector('[data-team-count]');

  socket.on('team_joined', (payload) => {
    if (count) count.textContent = payload.team_count;
    if (!list) return;

    list.querySelector('.team-list__empty')?.remove();
    // A team's phone re-emits join_room on reconnect; don't list it twice.
    const exists = [...list.children].some((li) => li.textContent === payload.team_name);
    if (exists) return;

    const item = document.createElement('li');
    item.textContent = payload.team_name;
    list.appendChild(item);
  });

  socket.on('answer_received', (payload) => {
    const text = document.querySelector('[data-answer-progress]');
    if (text) text.textContent = `${payload.answers_in} / ${payload.total_teams} answered`;
  });
});
