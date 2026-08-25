const { defineConfig } = require('@playwright/test');

module.exports = defineConfig({
  testDir: '.',
  testMatch: /dev-(ux|a11y)\.spec\.js/,
  timeout: 45_000,
  workers: 1,
  retries: 0,
  reporter: 'line',
  use: {
    browserName: 'chromium',
    headless: true,
    locale: 'en-US',
    timezoneId: 'UTC',
    colorScheme: 'dark',
    deviceScaleFactor: 1,
  },
  outputDir: '../../.orcan-dev-ux/artifacts/playwright',
});
