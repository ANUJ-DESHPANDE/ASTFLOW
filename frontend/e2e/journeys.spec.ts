/* Demo-critical user journeys against the real backend (no mocked search or graph responses).
 * Replaces the obsolete investigation.spec.ts, whose selectors (.result-card, a "Trace" nav button) belonged to a
 * removed UI. Requires `npm run demo` (semantic model available).
 */
import { test, expect, type Page } from '@playwright/test';

async function opened(page: Page) {
  await page.goto('/');
  await expect(page.locator('.monaco-editor')).toBeVisible();
}
async function ask(page: Page, question: string) {
  const box = page.getByLabel('Ask about your code');
  if (!(await box.isVisible())) await page.getByRole('button', { name: 'Ask', exact: true }).click();
  await box.fill(question);
  await page.getByLabel('Send question').click();
  await expect(page.locator('.conversation-turn').last().locator('h3')).toBeVisible();
  return page.locator('.conversation-turn').last();
}

test('usage question ranks the caller first and opens its exact lines', async ({ page }) => {
  await opened(page);
  const turn = await ask(page, 'Where is the Bluetooth settings deeplink used?');
  await expect(turn.locator('h3')).toHaveText('Here’s the relevant code');
  const first = turn.locator('.source-matches button').first();
  await expect(first).toContainText('BluetoothAgent.execute');
  await first.click();
  await expect(page.locator('.source-status')).toContainText('bluetooth/BluetoothAgent.js');
  await expect(page.locator('.source-highlight').first()).toBeVisible();
});

test('path question shows its observable second retrieval pass', async ({ page }) => {
  await opened(page);
  const turn = await ask(page, 'How does VoiceHandler reach BluetoothAgent?');
  await turn.locator('details.reasoning summary').click();
  const log = turn.locator('details.reasoning');
  await expect(log).toContainText('plan · Path investigation');
  await expect(log).toContainText('refine ·');
  await expect(log).toContainText('Second pass retrieved');
  await expect(log).toContainText('rank · Ranked');
  await expect(log).not.toContainText('rerank');
});

test('a question with no keyword evidence is not presented as the relevant code', async ({ page }) => {
  await opened(page);
  const turn = await ask(page, 'qxzjvnonexistentidentifier');
  await expect(turn.locator('h3')).toHaveText('Closest matches by meaning');
  await expect(turn).toContainText('No result shares a word or symbol with your question');
});

test('trace a path on a phone-sized screen without horizontal overflow', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await opened(page);
  await page.getByRole('navigation', { name: 'Workspace views' }).getByRole('button', { name: 'Map', exact: true }).click();
  await page.getByRole('button', { name: 'Trace a path' }).click();
  await page.getByRole('button', { name: 'Trace', exact: true }).click();
  await expect(page.locator('.canvas-caption')).toContainText('supported path');
  await expect(page.locator('.react-flow__edge').first()).toBeAttached();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
});

test('repository dialog indexes the demo working tree and returns to live source', async ({ page }) => {
  await opened(page);
  await page.getByLabel('Repository settings').click();
  await page.getByRole('button', { name: 'Use demo repository' }).click();
  const indexed = page.waitForResponse(r => r.url().endsWith('/api/index') && r.request().method() === 'POST');
  await page.getByRole('button', { name: 'Open & index' }).click();
  expect((await indexed).status()).toBe(202);
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(page.locator('.source-panel')).toBeVisible({ timeout: 30_000 });
  await expect(page.locator('.error-notice')).toHaveCount(0);
});

test('switching to the v1 snapshot shows v1 source, not the working tree', async ({ page }) => {
  await opened(page);
  await page.getByLabel('Repository version', { exact: true }).selectOption('v1');
  await page.getByTitle('auth/AuthService.js', { exact: true }).click();
  await expect(page.locator('.source-status')).toContainText('auth/AuthService.js');
  // v1 still owns session creation; v2 delegated it to SessionManager.
  await expect(page.locator('.monaco-editor .view-lines')).toContainText('createSession');
  await page.getByLabel('Repository version', { exact: true }).selectOption('v2');
  await page.getByTitle('auth/AuthService.js', { exact: true }).click();
  await expect(page.locator('.monaco-editor .view-lines')).toContainText('SessionManager');
});
