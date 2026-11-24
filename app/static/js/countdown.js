// Live question countdown, shared by the phones and the quiz master's screen.
// Display only: the server decides whether an answer is in time.
function createCountdown(bar) {
  const fill = bar.querySelector('[data-timer-fill]');
  const text = bar.querySelector('[data-timer-text]');
  let interval = null;

  function stop() {
    clearInterval(interval);
    interval = null;
    bar.hidden = true;
  }

  // remainingMs: time left now. totalSeconds: the full limit, for the bar width.
  function start(remainingMs, totalSeconds, onExpire) {
    stop();
    if (remainingMs === null || remainingMs === undefined) return; // no limit
    const endsAt = performance.now() + remainingMs;
    bar.hidden = false;

    const tick = () => {
      const left = Math.max(0, endsAt - performance.now());
      text.textContent = `${Math.ceil(left / 1000)}s`;
      fill.style.width = `${Math.min(100, (left / (totalSeconds * 1000)) * 100)}%`;
      bar.classList.toggle('timer-bar--urgent', left <= 10000);
      text.classList.toggle('timer-display--urgent', left > 0 && left <= 10000);
      if (left <= 0) {
        clearInterval(interval);
        interval = null;
        onExpire();
      }
    };
    interval = setInterval(tick, 200);
    tick();
  }

  return { start, stop };
}
