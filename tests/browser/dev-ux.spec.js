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
