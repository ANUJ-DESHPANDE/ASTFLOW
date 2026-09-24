import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './frontend/e2e', timeout: 60_000, workers: 1,
  use: { baseURL: 'http://127.0.0.1:8000', browserName: 'chromium',
    // Installed Microsoft Edge locally; CI sets PLAYWRIGHT_CHANNEL=chromium after `npx playwright install chromium`.
    channel: process.env.PLAYWRIGHT_CHANNEL || 'msedge',
    viewport: { width: 1440, height: 1000 }, screenshot: 'only-on-failure', trace: 'retain-on-failure' },
});
