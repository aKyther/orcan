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

  function ensureWebglFallback() {
    const url = new URL(window.location.href);
    if (url.searchParams.has("rendererType")) return false;
    const canvas = document.createElement("canvas");
    if (canvas.getContext("webgl2") || canvas.getContext("webgl")) return false;
    url.searchParams.set("rendererType", "canvas");
    url.searchParams.set("orcanRendererFallback", "no-webgl");
    window.location.replace(url);
    return true;
  }

  function ensureResponsiveFont() {
    const url = new URL(window.location.href);
    const width = window.visualViewport?.width || window.innerWidth;
    const desired = width <= PHONE_MAX_WIDTH_PX ? "16" : "14";
    const current = url.searchParams.get("fontSize");
    const marker = url.searchParams.get("orcanResponsiveFont");
    const managed = marker !== null;

    // An explicit fontSize always wins. Older URLs used marker=1; a changed
    // font value there is also explicit (otherwise editing ?fontSize=16 to
    // ?fontSize=22 would be immediately changed back by the phone profile).
    const explicit = current !== null && (
      !managed || (marker === "1" ? current !== desired : current !== marker)
    );
    if (explicit) {
      if (managed) {
        url.searchParams.delete("orcanResponsiveFont");
        window.history.replaceState(null, "", url);
      }
      return false;
    }

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
    if (desired === current && managed) return false;

    url.searchParams.set("fontSize", desired);
    // Store the value we set, rather than a boolean. It lets a user override
    // fontSize in a shared/adaptive URL without the stale marker winning.
    url.searchParams.set("orcanResponsiveFont", desired);
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

    // ttyd 1.7.7 can fit before its asynchronous renderer settles. Its fit
    // addon listens for resize, so refit after first paint and slow font/GPU init.
    for (const delay of [0, 100, 350]) {
      window.setTimeout(() => window.dispatchEvent(new Event("resize")), delay);
    }
    terminal.addEventListener("webglcontextlost", () => {
      const url = new URL(window.location.href);
      if (url.searchParams.get("rendererType") === "canvas") return;
      url.searchParams.set("rendererType", "canvas");
      url.searchParams.set("orcanRendererFallback", "context-lost");
      window.location.replace(url);
    }, true);
  }

  function installDiagnostics(terminal) {
    if (new URL(window.location.href).searchParams.get("orcanDiagnostics") !== "1"
        || document.querySelector("#orcan-render-diagnostics")) return;
    const viewport = window.visualViewport;
    const canvas = terminal.querySelector("canvas");
    const panel = document.createElement("output");
    panel.id = "orcan-render-diagnostics";
    panel.setAttribute("aria-live", "polite");
    panel.style.cssText = "position:fixed;right:8px;top:8px;z-index:10000;padding:6px 8px;"
      + "border:1px solid #554e61;border-radius:4px;background:#141119e8;color:#d8d2e2;"
      + "font:12px ui-monospace,monospace;pointer-events:none;white-space:pre-line";
    const update = () => {
      const url = new URL(window.location.href);
      const style = window.getComputedStyle(terminal);
      const fallback = url.searchParams.get("orcanRendererFallback");
      panel.textContent = [
        `renderer: ${url.searchParams.get("rendererType") || "server default"}`,
        `DPR: ${window.devicePixelRatio}; zoom: ${viewport?.scale || 1}`,
        `font: ${style.fontFamily}; ${style.fontSize}`,
        `canvas: ${canvas ? `${canvas.width}×${canvas.height}` : "not ready"}`,
        fallback ? `fallback: ${fallback}` : "",
      ].filter(Boolean).join("\n");
    };
    document.body.append(panel);
    update();
    window.addEventListener("resize", update);
    viewport?.addEventListener("resize", update);
  }

  function findTerminal() {
    const terminal = document.querySelector(".xterm");
    if (!terminal) return false;
    install(terminal);
    installDiagnostics(terminal);
    return true;
  }

  if (ensureWebglFallback()) return;
  if (ensureResponsiveFont()) return;

  if (!findTerminal()) {
    const observer = new MutationObserver(() => {
      if (findTerminal()) observer.disconnect();
    });
    observer.observe(document.documentElement, { childList: true, subtree: true });
  }
  installKeyboardViewportBridge();
})();
