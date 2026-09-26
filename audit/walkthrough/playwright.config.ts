import { defineConfig } from '@playwright/test';

// First-time-evaluator walkthrough (not part of the regular suite): run after scripts/judge_walkthrough.py has
// indexed express 4.18.2 / 4.19.2 / 4.21.2 into a running `npm run demo`.
export default defineConfig({
  testDir: '.', timeout: 600_000, workers: 1, reporter: 'list',
  use: { baseURL: 'http://127.0.0.1:8000', browserName: 'chromium', channel: process.env.PLAYWRIGHT_CHANNEL || 'chromium',
    viewport: { width: 1440, height: 900 },
    launchOptions: process.env.PW_CHROMIUM ? { executablePath: process.env.PW_CHROMIUM } : {} },
});
