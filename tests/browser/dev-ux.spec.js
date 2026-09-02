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
