/* Demo-critical user journeys against the real backend (no mocked search or graph responses).
 * Replaces the obsolete investigation.spec.ts, whose selectors (.result-card, a "Trace" nav button) belonged to a
 * removed UI. Requires `npm run demo` (semantic model available).
 */
import { test, expect, type Page } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';

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
  await expect(turn.locator('h3')).toHaveText('Source candidates to inspect');
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
  await expect(turn.locator('h3')).toHaveText('Source candidates to inspect');
  await expect(turn).toContainText('Inspect exact lines before drawing a conclusion');
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

test('grounded UI survives a repository update without stale source or map nodes', async ({ page }, testInfo) => {
  const runtimeErrors: string[] = [];
  page.on('pageerror', error => runtimeErrors.push(error.message));
  fs.mkdirSync('.astflow/screenshots', { recursive: true });
  const original = await (await page.request.get('/api/repository')).json();
  const fixture = testInfo.outputPath('grounding-repo');
  fs.cpSync(path.resolve('benchmark/fixtures/p003'), fixture, { recursive: true });
  try {
    await opened(page);
    await page.getByLabel('Repository settings').click();
    await page.getByRole('dialog').getByLabel('Repository path').fill(fixture);
    await page.getByRole('dialog').getByLabel('Snapshot').fill('working-tree');
    await page.getByRole('button', { name: 'Open & index' }).click();
    await expect(page.locator('.source-panel')).toBeVisible({ timeout: 30_000 });
    await page.screenshot({ path: '.astflow/screenshots/p004-indexed.png' });
    const definition = await ask(page, 'Where is placeOrder defined?');
    await expect(definition).toContainText('service.js::placeOrder');
    await definition.getByRole('button', { name: /service.js::placeOrder/ }).click();
    await expect(page.locator('.source-status')).toContainText('service.js');
    await page.screenshot({ path: '.astflow/screenshots/p004-citation.png' });
    const ambiguous = await ask(page, 'Where is config defined?');
    await expect(ambiguous.locator('h3')).toHaveText('Multiple symbols match');
    await expect(ambiguous).toContainText('helper.js::config');
    await expect(ambiguous).toContainText('repository.js::config');
    const absent = await ask(page, 'Where is the Kafka consumer implemented?');
    await expect(absent.locator('h3')).toHaveText('No verified implementation found');
    await page.screenshot({ path: '.astflow/screenshots/p004-negative.png' });
    await page.getByRole('navigation', { name: 'Workspace views' }).getByRole('button', { name: 'Map' }).click();
    await expect(page.locator('.react-flow__node').first()).toBeVisible();
    await page.screenshot({ path: '.astflow/screenshots/p004-map.png' });
    async function update() {
      const prior = (await (await page.request.get('/api/repository')).json()).indexes.find((entry: { version: string }) => entry.version === 'working-tree').version_key;
      await page.getByLabel('Reindex repository').click();
      await expect.poll(async () => (await (await page.request.get('/api/repository')).json()).indexes.find((entry: { version: string }) => entry.version === 'working-tree').version_key).not.toBe(prior);
      await expect(page.locator('.source-panel')).toBeVisible({ timeout: 30_000 });
    }
    fs.writeFileSync(path.join(fixture, 'new.js'), "export function newOrder() { return 'new'; }\n");
    await update();
    const updated = await ask(page, 'Where is newOrder defined?');
    await expect(updated).toContainText('new.js::newOrder');
    await page.screenshot({ path: '.astflow/screenshots/p004-updated.png' });
    await page.getByRole('navigation', { name: 'Workspace views' }).getByRole('button', { name: 'Map' }).click();
    await expect(page.getByLabel('Map file focus')).toContainText('new.js');
    fs.writeFileSync(path.join(fixture, 'new.js'), "export function changedOrder() { return 'changed'; }\n");
    await update();
    await expect((await ask(page, 'Where is newOrder defined?')).locator('h3')).toHaveText('No matching symbol found');
    await expect(await ask(page, 'Where is changedOrder defined?')).toContainText('new.js::changedOrder');
    fs.renameSync(path.join(fixture, 'new.js'), path.join(fixture, 'renamed.js'));
    await update();
    await expect(await ask(page, 'Where is changedOrder defined?')).toContainText('renamed.js::changedOrder');
    await page.getByRole('navigation', { name: 'Workspace views' }).getByRole('button', { name: 'Map' }).click();
    await expect(page.getByLabel('Map file focus')).toContainText('renamed.js');
    await expect(page.getByLabel('Map file focus')).not.toContainText('new.js');
    fs.unlinkSync(path.join(fixture, 'renamed.js'));
    await update();
    await expect((await ask(page, 'Where is changedOrder defined?')).locator('h3')).toHaveText('No matching symbol found');
    await page.getByRole('navigation', { name: 'Workspace views' }).getByRole('button', { name: 'Map' }).click();
    await expect(page.getByLabel('Map file focus')).not.toContainText('renamed.js');
    await expect(page.locator('.error-notice')).toHaveCount(0);
    expect(runtimeErrors).toEqual([]);
  } finally {
    for (const version of ['v1', 'v2', 'working-tree']) {
      const restored = await page.request.post('/api/index', { data: { repo_path: original.path, version, background: false } });
      expect(restored.ok()).toBeTruthy();
    }
  }
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

test('invalid repository indexing leaves an actionable error and recovers', async ({ page }) => {
  await opened(page);
  await page.getByLabel('Repository settings').click();
  await page.getByRole('dialog').getByLabel('Repository path').fill(path.resolve('missing-p004-repository'));
  await page.getByRole('button', { name: 'Open & index' }).click();
  await expect(page.locator('.error-notice[role=alert]')).toBeVisible({ timeout: 30_000 });
  await expect(page.locator('.workspace-empty').filter({ hasText: 'Reading your repository' })).toHaveCount(0);
  await page.getByLabel('Repository settings').click();
  await page.getByRole('button', { name: 'Use demo repository' }).click();
  await page.getByRole('button', { name: 'Open & index' }).click();
  await expect(page.locator('.source-panel')).toBeVisible({ timeout: 30_000 });
  await expect(page.locator('.error-notice')).toHaveCount(0);
});
