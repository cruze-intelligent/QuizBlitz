// Team phone: receives questions/reveals over Socket.IO and submits answers.
document.addEventListener('DOMContentLoaded', () => {
  const root = document.querySelector('[data-session-code]');
  if (!root || typeof io === 'undefined') return;
  const sessionCode = root.dataset.sessionCode;
  const teamId = Number(root.dataset.teamId);
  const teamName = root.dataset.teamName;

  const questionText = document.getElementById('question-text');
  const optionList = document.getElementById('option-list');
  const status = document.getElementById('status-message');

  const socket = io();
  socket.on('connect', () => socket.emit('join_room', { session_code: sessionCode, team_name: teamName }));

  socket.on('question_pushed', (payload) => {
    questionText.textContent = payload.question_text;
    document.getElementById('round-number').textContent = payload.round;
    document.getElementById('question-number').textContent = payload.question_num;
    status.textContent = '';
    optionList.innerHTML = '';

    payload.options.forEach((option) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'answer-option';
      button.dataset.optionId = option.id; // read back on reveal to highlight the correct option
      button.textContent = option.text;
      button.addEventListener('click', () => {
        socket.emit('submit_answer', { session_code: sessionCode, team_id: teamId, option_id: option.id });
        optionList.querySelectorAll('.answer-option').forEach((btn) => { btn.disabled = true; });
        button.classList.add('is-selected');
        status.textContent = 'Answer submitted!';
      });
      optionList.appendChild(button);
    });
  });

  socket.on('answer_revealed', (payload) => {
    optionList.querySelectorAll('.answer-option').forEach((btn) => {
      btn.disabled = true;
      if (Number(btn.dataset.optionId) === payload.correct_option_id) btn.classList.add('is-correct');
    });
    status.textContent = `Correct answer: ${payload.correct_option_text}`;
  });
});
