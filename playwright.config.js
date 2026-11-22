'use strict';
const { defineConfig } = require('@playwright/test');

module.exports = defineConfig({
  testDir: './tests',
  testMatch: ['**/workbench_browser_test.js', '**/console_browser_test.js'],
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  workers: 2,
  use: { baseURL: 'http://127.0.0.1:8765', trace: 'retain-on-failure' },
  webServer: {
    command: 'python3 tools/serve_workbench.py --port 8765',
    url: 'http://127.0.0.1:8765/satsift/',
    reuseExistingServer: false
  }
});
