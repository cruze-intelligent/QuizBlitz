document.addEventListener('DOMContentLoaded', () => {
  const socket = io();
  const room = document.body.dataset.sessionCode;
  if (!room) return;

  socket.emit('join_room', { session_code: room });

  socket.on('question_pushed', (payload) => {
    const questionText = document.getElementById('question-text');
    const optionList = document.getElementById('option-list');
    if (!questionText || !optionList) return;

    questionText.textContent = payload.question_text;
    optionList.innerHTML = '';

    payload.options.forEach((option) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'answer-option';
      button.dataset.optionId = option.id;
      button.textContent = option.text;
      button.addEventListener('click', () => {
        socket.emit('submit_answer', { session_code: room, team_id: Number(document.body.dataset.teamId), option_id: Number(option.id) });
        button.disabled = true;
      });
      optionList.appendChild(button);
    });
  });
});
