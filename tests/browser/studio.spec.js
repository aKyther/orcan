const { test: base, expect } = require('@playwright/test');
const { largeReport } = require('./studio-fixtures');
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

test('container creator invalidates readiness and approval when its target changes', async ({ page }) => {
  await page.locator('[data-view-target="enclaves"]').click();
  await page.locator('#new-container').click();
  await page.locator('#enclave-create-profile').selectOption('demo');
  await page.locator('#enclave-create-name').fill('reviewer');
  await expect(page.locator('#enclave-create-apply')).toBeDisabled();
  await page.locator('#enclave-create-check').click();
  await expect(page.locator('#enclave-create-plan')).toBeEnabled();
  await page.locator('#enclave-create-plan').click();
  await expect(page.locator('#enclave-create-apply')).toBeEnabled();
  await page.locator('#enclave-create-name').fill('tester');
  await expect(page.locator('#enclave-create-apply')).toBeDisabled();
  await expect(page.locator('#enclave-create-plan')).toBeDisabled();
  await page.locator('#container-create-cancel').click();
  await expect(page.locator('#enclave-creator')).toBeHidden();
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

test('100 projects keep filters, both anchors and workspace drafts consistent', async ({ page }) => {
  const report = largeReport();
  await page.unroute('**/preview-probe.json');
  await page.route('**/preview-probe.json', route => route.fulfill({ json: report }));
  await page.reload();
  await expect(page.locator('[data-profile-id="demo"]')).toHaveCount(1);
  await connect(page);
  const sourceChips = page.locator('#sandbox-tray .project-chip');
  await expect(sourceChips).toHaveCount(100);
  await page.locator('#map-focus-clear').click();
  await expect(page.locator('#workspace-cards .workspace-card:not(.new-workspace)')).toHaveCount(10);
  const gitFilter = page.locator('[data-map-filter="git"]');
  await gitFilter.click();
  await expect(sourceChips).toHaveCount(80);
  await gitFilter.click();
  await expect(gitFilter).not.toHaveClass(/active/);
  await expect(sourceChips).toHaveCount(100);

  const card = name => page.locator('#workspace-cards .workspace-card').filter({ has: page.locator('header > strong', { hasText: name }) });
  await card('work-00').locator('header > strong').click();
  await expect(page.locator('#trace-lines path.highlight')).toHaveCount(report.context.workspaces[0].projects.length);
  for (const width of [1280, 640]) {
    await page.setViewportSize({ width, height: 900 });
    await expect.poll(() => page.evaluate(() => {
      const bounds = document.querySelector('#context-canvas').getBoundingClientRect();
      const center = node => { const box = node.getBoundingClientRect(); return { x: box.left - bounds.left + box.width / 2, y: box.top - bounds.top + box.height / 2 }; };
      const links = [...document.querySelectorAll('#trace-lines path.highlight')];
      return links.length > 0 && links.every(line => {
        const path = line.dataset.projectPath;
        const source = [...document.querySelectorAll('#sandbox-tray .project-chip')].find(chip => chip.dataset.projectPath === path)?.querySelector('.connection-anchor');
        const target = [...document.querySelectorAll('#workspace-cards .project-chip')].find(chip => chip.dataset.projectPath === path && chip.dataset.workspace === line.dataset.workspace)?.querySelector('.connection-anchor');
        if (!source || !target) return false;
        const start = line.getPointAtLength(0), end = line.getPointAtLength(line.getTotalLength());
        const first = center(source), last = center(target);
        return Math.abs(start.x - first.x) < 1 && Math.abs(start.y - first.y) < 1 && Math.abs(end.x - last.x) < 1 && Math.abs(end.y - last.y) < 1;
      });
    })).toBe(true);
  }
  const source = sourceChips.filter({ hasText: 'project-099' });
  const transfer = await page.evaluateHandle(() => new DataTransfer());
  await source.dispatchEvent('dragstart', { dataTransfer: transfer });
  await card('work-00').dispatchEvent('drop', { dataTransfer: transfer });
  await source.dispatchEvent('dragend', { dataTransfer: transfer });
  await expect(page.locator('#plan-dialog')).toBeVisible();
  await page.locator('#plan-confirm').click();
  await expect(page.locator('#change-set-count')).toContainText('1 change');
  // Toggle focus off, inspect another workspace, then return to the draft.
  await card('work-00').locator('header > strong').click();
  await card('work-01').locator('header > strong').click();
  await expect(page.locator('#change-set-count')).toContainText('1 change');
  await card('work-01').locator('header > strong').click();
  await card('work-00').locator('header > strong').click();
  await expect(card('work-00').locator('.planned-project')).toHaveCount(1);
  await card('work-00').locator('.workspace-draft-discard').click();
  await page.locator('.studio-dialog').getByRole('button', { name: 'Discard', exact: true }).click();
  await expect(card('work-00').locator('.project-chip')).toHaveCount(report.context.workspaces[0].projects.length);
  await expect(page.locator('#change-set')).toBeHidden();
});
