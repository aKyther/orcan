const { test, expect } = require('@playwright/test');

const baseURL = process.env.ORCAN_DEV_UX_URL || 'http://127.0.0.1:17681';

async function assertTerminalReady(page) {
  await page.goto(baseURL, { waitUntil: 'domcontentloaded' });
  await expect(page.locator('.xterm')).toBeVisible({ timeout: 15_000 });
  await expect(page.locator('.xterm-screen')).toBeVisible();
  await page.waitForTimeout(1_000);
  const dimensions = await page.locator('.xterm-screen').evaluate((element) => ({
    width: element.getBoundingClientRect().width,
    height: element.getBoundingClientRect().height,
    bodyWidth: document.documentElement.scrollWidth,
    viewportWidth: document.documentElement.clientWidth,
  }));
  expect(dimensions.width).toBeGreaterThan(400);
  expect(dimensions.height).toBeGreaterThan(250);
  expect(dimensions.bodyWidth).toBeLessThanOrEqual(dimensions.viewportWidth);
}

test('developer UX remains readable at desktop and compact sizes', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await assertTerminalReady(page);
  await expect(page).toHaveScreenshot('dev-ux-desktop.png', {
    animations: 'disabled',
    maxDiffPixelRatio: 0.08,
  });

  await page.setViewportSize({ width: 900, height: 700 });
  await assertTerminalReady(page);
  await expect(page).toHaveScreenshot('dev-ux-compact.png', {
    animations: 'disabled',
    maxDiffPixelRatio: 0.08,
  });
});

test('one-finger vertical drag becomes wheel input', async ({ page }) => {
  await assertTerminalReady(page);
  const result = await page.locator('.xterm').evaluate((terminal) => {
    const wheelDeltas = [];
    terminal.addEventListener('wheel', (event) => wheelDeltas.push(event.deltaY), { capture: true });
    const touch = (x, y) => new Touch({
      identifier: 1, target: terminal, clientX: x, clientY: y,
    });
    terminal.dispatchEvent(new TouchEvent('touchstart', {
      bubbles: true, touches: [touch(100, 200)],
    }));
    terminal.dispatchEvent(new TouchEvent('touchmove', {
      bubbles: true, cancelable: true, touches: [touch(102, 170)],
    }));
    terminal.dispatchEvent(new TouchEvent('touchend', { bubbles: true, touches: [] }));
    return { installed: terminal.dataset.orcanTouchScroll, wheelDeltas };
  });
  expect(result.installed).toBe('on');
  expect(result.wheelDeltas).toEqual([30]);
});

test('phone font and keyboard viewport keep input visible', async ({ page }) => {
  await page.setViewportSize({ width: 480, height: 700 });
  await page.goto(baseURL);
  await page.waitForURL(/fontSize=16/);
  const input = page.locator('.xterm-helper-textarea');
  await input.waitFor();
  await input.focus();
  await page.setViewportSize({ width: 480, height: 420 });
  await page.waitForTimeout(100);

  const state = await page.evaluate(() => ({
    bridge: document.body.dataset.orcanKeyboardBridge,
    keyboard: document.body.dataset.orcanKeyboardViewport,
    bodyHeight: document.body.style.height,
    containerHeight: document.querySelector('#terminal-container')?.style.height,
    viewportHeight: Math.round(window.visualViewport?.height || 0),
    terminalBottom: Math.round(document.querySelector('.xterm')?.getBoundingClientRect().bottom || 0),
  }));
  expect(state.bridge).toBe('on');
  expect(state.keyboard).toBe('open');
  expect(parseInt(state.bodyHeight, 10)).toBe(state.viewportHeight);
  expect(parseInt(state.containerHeight, 10)).toBe(state.viewportHeight);
  expect(state.terminalBottom).toBeLessThanOrEqual(state.viewportHeight);
});

test('desktop keeps the server-configured font', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(baseURL);
  await page.waitForSelector('.xterm');
  expect(new URL(page.url()).searchParams.has('fontSize')).toBe(false);
  expect(new URL(page.url()).searchParams.has('orcanResponsiveFont')).toBe(false);
});
