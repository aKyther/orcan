const { defineConfig } = require('@playwright/test');
const path = require('node:path');

module.exports = defineConfig({
  testDir: '.',
  testMatch: 'studio.spec.js',
  timeout: 30_000,
  workers: 1,
  reporter: [['line'], ['json', { outputFile: path.resolve(__dirname, '../../.orcan-dev-ux/artifacts/studio-browser/results.json') }]],
  use: { browserName: 'chromium', headless: true, baseURL: 'http://127.0.0.1:1438', viewport: { width: 1280, height: 900 } },
  outputDir: '../../.orcan-dev-ux/artifacts/studio-browser',
  webServer: {
    command: 'npm run dev -- --port 1438 --strictPort',
    cwd: '../../studio/app',
    url: 'http://127.0.0.1:1438',
    reuseExistingServer: false,
  },
});
