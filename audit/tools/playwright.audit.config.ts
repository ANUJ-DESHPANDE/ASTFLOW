import { defineConfig } from '@playwright/test';

// Audit-only crawler (not part of the product E2E suite). Requires `npm run demo` on 127.0.0.1:8000.
export default defineConfig({
  testDir: '.', testMatch: /.*\.audit\.ts/, timeout: 60 * 60_000, workers: 1,
  use: { actionTimeout: 10_000, navigationTimeout: 30_000, baseURL: 'http://127.0.0.1:8000', browserName: 'chromium', channel: 'msedge',
    viewport: { width: 1440, height: 1000 }, permissions: ['clipboard-read', 'clipboard-write'] },
});
