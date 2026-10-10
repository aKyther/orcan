const { test: base, expect } = require('@playwright/test');
const test = base.extend({
  runtimeErrors: [async ({ page }, use) => {
    const errors = [];
    page.on('pageerror', error => errors.push(error.stack ?? error.message));
    await use();
    expect(errors).toEqual([]);
  }, { auto: true }],
});

test.beforeEach(async ({ page }) => {
  // Always use bundled fixtures, never a developer's host snapshot.
  await page.route('**/preview-probe.json', route => route.fulfill({ status: 404, body: '' }));
  await page.goto('/?demo=1');
  await expect(page.locator('[data-profile-id="demo"]')).toHaveCount(1);
});

async function connect(page) {
  await page.locator('[data-view-target="enclaves"]').click();
  await page.locator('[data-profile-id="demo"]').click();
  await expect(page.locator('#context-canvas')).toBeVisible();
  await expect(page.locator('#workspace-cards .project-chip').first()).toBeVisible();
}

test('connection gates context operations and disconnected profiles stay usable', async ({ page }) => {
  await expect(page.locator('[data-view-target="contexts"]')).toBeHidden();
  await page.locator('[data-view-target="profiles"]').click();
  await expect(page.locator('[data-view="profiles"]')).toBeVisible();
  await connect(page);
  await expect(page.locator('[data-view-target="contexts"]')).toBeVisible();
});

test('selection preserves cards and connection anchors follow desktop and narrow layout', async ({ page }) => {
  await connect(page);
  const chip = page.locator('#sandbox-tray .project-chip').first();
  const path = await chip.getAttribute('data-project-path');
  await page.evaluate(() => { window.originalWorkspaceCard = document.querySelector('#workspace-cards .workspace-card'); });
  await chip.click();
  await expect(chip).toHaveClass(/traced/);
  expect(await page.evaluate(() => window.originalWorkspaceCard === document.querySelector('#workspace-cards .workspace-card'))).toBe(true);
  for (const width of [1280, 640]) {
    await page.setViewportSize({ width, height: 900 });
    await expect.poll(() => page.evaluate(path => {
      const canvas = document.querySelector('#context-canvas').getBoundingClientRect();
      const source = [...document.querySelectorAll('#sandbox-tray .project-chip')].find(chip => chip.dataset.projectPath === path)?.querySelector('.connection-anchor')?.getBoundingClientRect();
      const lines = [...document.querySelectorAll('#trace-lines path')];
      if (!source || !lines.length) return false;
      const line = lines.find(line => line.classList.contains('highlight'));
      const point = line?.getPointAtLength(0);
      return Boolean(point && Math.abs(point.x - (source.left - canvas.left + source.width / 2)) < 1 && Math.abs(point.y - (source.top - canvas.top + source.height / 2)) < 1);
    }, path)).toBe(true);
  }
});

test('drag stages a draft and discard leaves the workspace unchanged', async ({ page }) => {
  await connect(page);
  const source = page.locator('#sandbox-tray .project-chip[data-project-path$="/scratch"]');
  const path = await source.getAttribute('data-project-path');
  const target = page.locator('#workspace-cards .workspace-card').first();
  const original = await target.locator('.project-chip').count();
  const transfer = await page.evaluateHandle(() => new DataTransfer());
  await source.dispatchEvent('dragstart', { dataTransfer: transfer });
  await target.dispatchEvent('drop', { dataTransfer: transfer });
  await source.dispatchEvent('dragend', { dataTransfer: transfer });
  await expect(page.locator('#plan-dialog')).toBeVisible();
  await expect(page.locator('#plan-confirm')).toBeEnabled();
  await page.locator('#plan-confirm').click();
  await expect(page.locator('#change-set-count')).toContainText('1 change');
  await page.locator('.workspace-draft-discard').first().click();
  await page.locator('.studio-dialog').getByRole('button', { name: 'Discard', exact: true }).click();
  await expect(page.locator('#change-set')).toBeHidden();
  expect(await target.locator('.project-chip').count()).toBe(original);
  expect(await page.locator('#workspace-cards .project-chip').evaluateAll((chips, path) => chips.filter(chip => chip.dataset.projectPath === path && chip.dataset.connectionState === 'planned').length, path)).toBe(0);
});
