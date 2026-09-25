import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './frontend/e2e', timeout: 60_000, workers: 1,
  // On GitHub Actions, failing tests also appear as annotations on the public run page.
  reporter: process.env.GITHUB_ACTIONS ? [['github'], ['list']] : 'list',
  use: { baseURL: process.env.PLAYWRIGHT_BASE_URL || 'http://127.0.0.1:8000', browserName: 'chromium',
    // Installed Microsoft Edge locally; CI sets PLAYWRIGHT_CHANNEL=chromium after `npx playwright install chromium`.
    channel: process.env.PLAYWRIGHT_CHANNEL || 'msedge',
    viewport: { width: 1440, height: 1000 }, screenshot: 'only-on-failure', trace: 'retain-on-failure' },
});
