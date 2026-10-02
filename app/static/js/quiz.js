/**
 * quiz.js — Single-page quiz player logic.
 *
 * Reads questions from the embedded <script id="questions-data"> JSON blob
 * (which contains NO is_correct field — the answer key lives only on the server).
 *
 * Responsibilities:
 *   - Render question cards into #question-container
 *   - Show one question at a time; hide others
 *   - Track selected options in a JS object: { question_id: option_id }
 *   - Highlight selected option button
 *   - "Next / Previous" navigation
 *   - Show "Submit" button on the last question
 *   - Update progress bar and label
 *   - Populate #answers-input with JSON before form submission
 *
 * serializeAnswers() is also called by timer.js on expiry.
 */

(function () {
  "use strict";

  // ── Data ──────────────────────────────────────────────────────────────────

  const dataEl   = document.getElementById("questions-data");
  const container = document.getElementById("question-container");
  const quizForm = document.getElementById("quiz-form");

  if (!dataEl || !container || !quizForm) return;

  const questions = JSON.parse(dataEl.textContent || "[]");
  if (questions.length === 0) return;

  let currentIndex = 0;
  const answers = {};   // { question_id (string): option_id (string) }

  // ── DOM helpers ──────────────────────────────────────────────────────────

  const btnPrev    = document.getElementById("btn-prev");
  const btnNext    = document.getElementById("btn-next");
  const btnSubmit  = document.getElementById("btn-submit");
  const answersInput = document.getElementById("answers-input");
  const progressLabel = document.getElementById("progress-label");
  const progressFill  = document.getElementById("progress-fill");
  const progressTrack = document.getElementById("progress-track");

  // ── Render ───────────────────────────────────────────────────────────────

  /** Build all question card elements and append to the container. */
  function buildQuestions() {
    questions.forEach((q, idx) => {
      const card = document.createElement("div");
      card.classList.add("question-card");
      card.dataset.idx = idx;
      card.setAttribute("role", "group");
      card.setAttribute("aria-label", `Question ${idx + 1}`);
      if (idx !== 0) card.classList.add("question-card--hidden");

      // Question text
      const qText = document.createElement("p");
      qText.classList.add("question-text");
      qText.textContent = q.text;

      // Options list
      const optList = document.createElement("ul");
      optList.classList.add("option-list");
      optList.setAttribute("role", "list");

      q.options.forEach(opt => {
        const li = document.createElement("li");
        li.classList.add("option-item");

        const btn = document.createElement("button");
        btn.type = "button";
        btn.classList.add("option-btn");
        btn.dataset.questionId = q.id;
        btn.dataset.optionId   = opt.id;
        btn.id = `opt-${q.id}-${opt.id}`;
        btn.textContent = opt.text;

        // Restore previous selection (e.g. navigating back)
        if (answers[String(q.id)] === String(opt.id)) {
          btn.classList.add("option-btn--selected");
        }

        btn.addEventListener("click", () => selectOption(q.id, opt.id, idx));

        li.appendChild(btn);
        optList.appendChild(li);
      });

      card.appendChild(qText);
      card.appendChild(optList);
      container.appendChild(card);
    });
  }

  // ── Selection ────────────────────────────────────────────────────────────

  /** Handle an option selection for question qId at card index cardIdx. */
  function selectOption(qId, optId, cardIdx) {
    answers[String(qId)] = String(optId);

    // Update button highlight within this card
    const card = container.querySelector(`.question-card[data-idx="${cardIdx}"]`);
    card.querySelectorAll(".option-btn").forEach(b => {
      b.classList.toggle("option-btn--selected", String(b.dataset.optionId) === String(optId));
    });
  }

  // ── Navigation ───────────────────────────────────────────────────────────

  function showQuestion(idx) {
    container.querySelectorAll(".question-card").forEach((card, i) => {
      card.classList.toggle("question-card--hidden", i !== idx);
    });

    currentIndex = idx;

    // Progress bar
    const pct = ((idx + 1) / questions.length) * 100;
    if (progressFill)  progressFill.style.width = `${pct}%`;
    if (progressLabel) progressLabel.textContent = `Question ${idx + 1} of ${questions.length}`;
    if (progressTrack) progressTrack.setAttribute("aria-valuenow", idx + 1);

    // Nav buttons
    btnPrev.disabled = idx === 0;

    const isLast = idx === questions.length - 1;
    btnNext.style.display   = isLast ? "none" : "inline-flex";
    btnSubmit.style.display = isLast ? "inline-flex" : "none";
  }

  btnPrev.addEventListener("click", () => {
    if (currentIndex > 0) showQuestion(currentIndex - 1);
  });

  btnNext.addEventListener("click", () => {
    if (currentIndex < questions.length - 1) showQuestion(currentIndex + 1);
  });

  // ── Serialise & Submit ────────────────────────────────────────────────────

  /**
   * Populate the hidden #answers-input with the current answers JSON.
   * Called both on manual submit and by timer.js on expiry (via global ref).
   */
  window.serializeAnswers = function () {
    if (answersInput) {
      answersInput.value = JSON.stringify(answers);
    }
  };

  quizForm.addEventListener("submit", (e) => {
    serializeAnswers();
    // Allow the form to submit normally
  });

  // ── Init ──────────────────────────────────────────────────────────────────

  buildQuestions();
  showQuestion(0);
})();
