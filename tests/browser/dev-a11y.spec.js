const { test, expect } = require('@playwright/test');
const { AxeBuilder } = require('@axe-core/playwright');

const baseURL = process.env.ORCAN_DEV_UX_URL || 'http://127.0.0.1:17681';

test('developer terminal is keyboard reachable and has no serious a11y violations', async ({ page }) => {
  await page.setViewportSize({ width: 900, height: 700 });
  await page.goto(baseURL, { waitUntil: 'domcontentloaded' });
  await expect(page.locator('.xterm')).toBeVisible({ timeout: 15_000 });

  const dimensions = await page.evaluate(() => ({
    bodyWidth: document.documentElement.scrollWidth,
    viewportWidth: document.documentElement.clientWidth,
    bodyHeight: document.documentElement.scrollHeight,
    viewportHeight: document.documentElement.clientHeight,
  }));
  expect(dimensions.bodyWidth).toBeLessThanOrEqual(dimensions.viewportWidth);
  expect(dimensions.bodyHeight).toBeLessThanOrEqual(dimensions.viewportHeight);

  await page.keyboard.press('Tab');
  const focus = await page.evaluate(() => {
    const element = document.activeElement;
    if (!element) return null;
    const rect = element.getBoundingClientRect();
    const terminal = element.closest('.xterm');
    const terminalRect = terminal && terminal.getBoundingClientRect();
    return {
      tag: element.tagName,
      id: element.id,
      visible: (rect.width > 0 && rect.height > 0) ||
        Boolean(terminalRect && terminalRect.width > 0 && terminalRect.height > 0),
    };
  });
  expect(focus).not.toBeNull();
  expect(focus.visible).toBe(true);

  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa'])
    .analyze();
  const serious = results.violations.filter((violation) =>
    violation.impact === 'serious' || violation.impact === 'critical',
  );
  expect(serious, JSON.stringify(serious, null, 2)).toEqual([]);

  await page.setViewportSize({ width: 480, height: 320 });
  await page.reload({ waitUntil: 'domcontentloaded' });
  await expect(page.locator('.xterm')).toBeVisible({ timeout: 15_000 });
  const tiny = await page.evaluate(() => ({
    bodyWidth: document.documentElement.scrollWidth,
    viewportWidth: document.documentElement.clientWidth,
    bodyHeight: document.documentElement.scrollHeight,
    viewportHeight: document.documentElement.clientHeight,
    terminalWidth: document.querySelector('.xterm')?.getBoundingClientRect().width || 0,
    terminalHeight: document.querySelector('.xterm')?.getBoundingClientRect().height || 0,
  }));
  expect(tiny.bodyWidth).toBeLessThanOrEqual(tiny.viewportWidth);
  expect(tiny.bodyHeight).toBeLessThanOrEqual(tiny.viewportHeight);
  expect(tiny.terminalWidth).toBeGreaterThan(200);
  expect(tiny.terminalHeight).toBeGreaterThan(120);
});
