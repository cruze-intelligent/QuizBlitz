/**
 * timer.js — Countdown timer for the quiz play page.
 *
 * Reads the time limit from:  data-seconds="<N>" on #timer-bar
 *
 * Updates:
 *   #timer-display  — MM:SS text
 *   #timer-fill     — shrinking progress bar
 *
 * Behaviour:
 *   - Turns the timer red when < 10 seconds remain
 *   - Auto-submits the quiz form when time expires
 */

(function () {
  "use strict";

  const timerBar   = document.getElementById("timer-bar");
  const timerFill  = document.getElementById("timer-fill");
  const display    = document.getElementById("timer-display");
  const quizForm   = document.getElementById("quiz-form");

  if (!timerBar || !display || !quizForm) return;  // not on play page

  const TOTAL_SECONDS = parseInt(timerBar.dataset.seconds, 10) || 60;
  let remaining = TOTAL_SECONDS;

  /** Format seconds → MM:SS */
  function fmt(s) {
    const m = Math.floor(s / 60);
    const sec = s % 60;
    return `${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
  }

  /** Update the visual fill bar (CSS width) */
  function updateFill() {
    const pct = (remaining / TOTAL_SECONDS) * 100;
    if (timerFill) timerFill.style.width = `${pct}%`;
  }

  /** Render one tick */
  function tick() {
    display.textContent = fmt(remaining);
    updateFill();

    // Turn red in the last 10 seconds
    if (remaining <= 10) {
      timerBar.classList.add("timer-bar--urgent");
      display.classList.add("timer-display--urgent");
    }

    if (remaining <= 0) {
      clearInterval(interval);
      display.textContent = "00:00";
      // Auto-submit: JS serialises answers into the hidden field first
      if (typeof serializeAnswers === "function") {
        serializeAnswers();
      }
      quizForm.submit();
      return;
    }

    remaining--;
  }

  // Initialise immediately so there's no 1-second visible lag
  tick();
  remaining--;  // already rendered 0-th tick

  const interval = setInterval(tick, 1000);
})();
