/* Touch-only scroll bridge for ttyd/xterm.js.
 * xterm disables native touch scrolling while tmux mouse tracking is active.
 */
(() => {
  "use strict";

  const DRAG_THRESHOLD_PX = 10;
  let startX = 0;
  let startY = 0;
  let previousY = 0;
  let dragging = false;

  function install(terminal) {
    if (terminal.dataset.orcanTouchScroll === "on") return;
    terminal.dataset.orcanTouchScroll = "on";
    terminal.style.touchAction = "none";

    terminal.addEventListener("touchstart", (event) => {
      if (event.touches.length !== 1) {
        dragging = false;
        return;
      }
      const touch = event.touches[0];
      startX = touch.clientX;
      startY = touch.clientY;
      previousY = touch.clientY;
      dragging = false;
    }, { passive: true });

    terminal.addEventListener("touchmove", (event) => {
      if (event.touches.length !== 1) return;
      const touch = event.touches[0];
      const totalX = touch.clientX - startX;
      const totalY = touch.clientY - startY;
      if (!dragging) {
        if (Math.hypot(totalX, totalY) < DRAG_THRESHOLD_PX) return;
        if (Math.abs(totalY) <= Math.abs(totalX)) return;
        dragging = true;
      }

      const deltaY = previousY - touch.clientY;
      previousY = touch.clientY;
      if (!deltaY) return;
      event.preventDefault();
      terminal.dispatchEvent(new WheelEvent("wheel", {
        bubbles: true,
        cancelable: true,
        clientX: touch.clientX,
        clientY: touch.clientY,
        deltaMode: WheelEvent.DOM_DELTA_PIXEL,
        deltaY,
      }));
    }, { passive: false });

    terminal.addEventListener("touchend", () => { dragging = false; }, { passive: true });
    terminal.addEventListener("touchcancel", () => { dragging = false; }, { passive: true });
  }

  function findTerminal() {
    const terminal = document.querySelector(".xterm");
    if (!terminal) return false;
    install(terminal);
    return true;
  }

  if (!findTerminal()) {
    const observer = new MutationObserver(() => {
      if (findTerminal()) observer.disconnect();
    });
    observer.observe(document.documentElement, { childList: true, subtree: true });
  }
})();
