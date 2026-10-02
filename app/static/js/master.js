document.addEventListener('DOMContentLoaded', () => {
  const socket = io();
  const room = document.body.dataset.sessionCode;
  if (!room) return;

  socket.emit('join_room', { session_code: room });

  socket.on('team_joined', (payload) => {
    const list = document.querySelector('.team-list');
    if (!list) return;
    const item = document.createElement('li');
    item.textContent = payload.team_name;
    list.appendChild(item);
  });

  socket.on('answer_received', (payload) => {
    const text = document.querySelector('[data-answer-progress]');
    if (text) {
      text.textContent = `${payload.answers_in} / ${payload.total_teams} answered`;
    }
  });
});
