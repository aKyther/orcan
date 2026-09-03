/* Touch-only scroll bridge for ttyd/xterm.js.
 * xterm disables native touch scrolling while tmux mouse tracking is active.
 */
(() => {
  "use strict";

  const DRAG_THRESHOLD_PX = 10;
  const KEYBOARD_THRESHOLD_PX = 120;
  const PHONE_MAX_WIDTH_PX = 600;
  const TABLET_MAX_WIDTH_PX = 1024;
  let startX = 0;
  let startY = 0;
  let previousY = 0;
  let dragging = false;
  let largestViewportHeight = window.visualViewport?.height || window.innerHeight;
  let appliedViewportHeight = 0;
  let resizeFrame = 0;

  function ensureResponsiveFont() {
    const url = new URL(window.location.href);
    const managed = url.searchParams.get("orcanResponsiveFont") === "1";
    // A fontSize explicitly supplied by the user always wins.
    if (url.searchParams.has("fontSize") && !managed) return false;

    const width = window.visualViewport?.width || window.innerWidth;
    // Desktop uses ttyd's server-side TTYD_FONT_SIZE. Only smaller touch
    // layouts need a browser override. Returning to desktop removes our
    // managed override so the configured value wins again.
    if (width > TABLET_MAX_WIDTH_PX) {
      if (!managed) return false;
      url.searchParams.delete("fontSize");
      url.searchParams.delete("orcanResponsiveFont");
      window.location.replace(url);
      return true;
    }
    const desired = width <= PHONE_MAX_WIDTH_PX ? "16" : "14";
    const current = url.searchParams.get("fontSize");
    if (desired === current && managed) return false;

    url.searchParams.set("fontSize", desired);
    url.searchParams.set("orcanResponsiveFont", "1");
    window.location.replace(url);
    return true;
  }

  function terminalInputFocused() {
    return document.activeElement?.classList.contains("xterm-helper-textarea") || false;
  }

  function syncKeyboardViewport() {
    resizeFrame = 0;
    const viewport = window.visualViewport;
    if (!viewport) return;
    const focused = terminalInputFocused();
    if (!focused) largestViewportHeight = Math.max(largestViewportHeight, viewport.height);
    const keyboardOpen = focused
      && largestViewportHeight - viewport.height >= KEYBOARD_THRESHOLD_PX;
    const height = keyboardOpen ? Math.round(viewport.height) : 0;
    if (height === appliedViewportHeight) return;
    appliedViewportHeight = height;

    document.documentElement.style.height = height ? `${height}px` : "";
    document.body.style.height = height ? `${height}px` : "";
    const container = document.querySelector("#terminal-container");
    if (container) container.style.height = height ? `${height}px` : "";
    document.body.dataset.orcanKeyboardViewport = height ? "open" : "closed";
    // ttyd's fit addon listens to window resize, not VisualViewport resize.
    window.dispatchEvent(new Event("resize"));
  }

  function scheduleKeyboardViewportSync() {
    if (resizeFrame) cancelAnimationFrame(resizeFrame);
    resizeFrame = requestAnimationFrame(syncKeyboardViewport);
  }

  function installKeyboardViewportBridge() {
    const viewport = window.visualViewport;
    if (!viewport || document.body.dataset.orcanKeyboardBridge === "on") return;
    document.body.dataset.orcanKeyboardBridge = "on";
    viewport.addEventListener("resize", scheduleKeyboardViewportSync);
    viewport.addEventListener("scroll", scheduleKeyboardViewportSync);
    document.addEventListener("focusin", scheduleKeyboardViewportSync);
    document.addEventListener("focusout", scheduleKeyboardViewportSync);
  }

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

  if (ensureResponsiveFont()) return;

  if (!findTerminal()) {
    const observer = new MutationObserver(() => {
      if (findTerminal()) observer.disconnect();
    });
    observer.observe(document.documentElement, { childList: true, subtree: true });
  }
  installKeyboardViewportBridge();
})();
