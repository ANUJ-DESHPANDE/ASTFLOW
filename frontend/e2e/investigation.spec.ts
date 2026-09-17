import { expect, test } from '@playwright/test';
import fs from 'node:fs';

test('live search opens exact source in a local Monaco editor', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('/');
  await expect(page.locator('.result-card').first()).toBeVisible();
  await expect(page.locator('.result-card').first()).toContainText('Bluetooth');
  fs.mkdirSync('.astflow/screenshots', { recursive: true });
  await page.screenshot({ path: '.astflow/screenshots/search.png', fullPage: true });
  const search = await page.request.post('/api/search', { data: { query: 'Where is Bluetooth settings handled?' } });
  const data = await search.json();
  await page.locator('.result-card').first().click();
  await expect(page.getByRole('region', { name: 'Source viewer' })).toBeVisible();
  await expect(page.locator('.monaco-editor')).toBeVisible();
  await expect(page.locator('.source-toolbar')).toContainText(data.results[0].file_path);
  await expect(page.locator('.source-location')).toContainText(`L${data.results[0].start_line}–${data.results[0].end_line}`);
  await page.screenshot({ path: '.astflow/screenshots/source.png', fullPage: true });
  expect(errors).toEqual([]);
});

test('trace graph edge opens its actual call site', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('.result-card').first()).toBeVisible();
  await page.getByRole('navigation').getByRole('button', { name: 'Trace', exact: true }).click();
  await page.getByRole('button', { name: 'Trace path', exact: true }).click();
  await expect(page.locator('.graph-message')).toContainText('supported path');
  await expect(page.locator('.react-flow__node').first()).toBeVisible();
  await page.screenshot({ path: '.astflow/screenshots/trace.png', fullPage: true });
  await page.locator('.react-flow__edge').first().click({ force: true });
  await expect(page.getByRole('region', { name: 'Source viewer' })).toBeVisible();
  await expect(page.locator('.edge-evidence')).toContainText('STATIC VERIFIED');
  await expect(page.locator('.edge-evidence code')).not.toBeEmpty();
});

test('version comparison renders real session refactor and source', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('.result-card').first()).toBeVisible();
  await page.getByLabel('Search repository').fill('Where is session restoration handled?');
  await page.getByRole('navigation').getByRole('button', { name: 'Changes' }).click();
  await page.getByLabel('Version A').selectOption('v1');
  await page.getByLabel('Version B').selectOption('v2');
  await page.getByRole('button', { name: 'Compare', exact: true }).click();
  await expect(page.locator('.comparison-columns')).toContainText('SessionManager.restore');
  await expect(page.locator('.change-stats')).toContainText('relevant symbols added');
  await page.screenshot({ path: '.astflow/screenshots/changes.png', fullPage: true });
  await page.locator('.comparison-columns .result-card').first().click();
  await expect(page.locator('.source-panel')).toBeVisible();
});

test('structural question performs observable second retrieval pass', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('.result-card').first()).toBeVisible();
  await page.getByLabel('Search repository').fill('How does VoiceHandler reach BluetoothAgent?');
  await page.getByRole('button', { name: 'Search', exact: true }).last().click();
  await expect(page.locator('.panel-heading')).toContainText('2 passes');
  await expect(page.locator('.activity-timeline')).toContainText('Refine investigation');
  await expect(page.locator('.activity-timeline')).toContainText('Second pass retrieved');
});

test('reindexing from the UI reports progress and returns live results', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('.result-card').first()).toBeVisible();
  await page.getByRole('button', { name: 'Reindex repository' }).click();
  await expect(page.locator('.index-progress')).toBeVisible();
  await expect(page.locator('.index-progress')).not.toBeVisible();
  await expect(page.locator('.result-card').first()).toBeVisible();
  await expect(page.locator('.index-state strong')).toHaveText('Index ready');
});

test('mobile layout can navigate search and trace without horizontal overflow', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  await expect(page.locator('.result-card').first()).toBeVisible();
  const nav = page.getByRole('navigation', { name: 'Mobile investigation views' });
  await expect(nav).toBeVisible();
  await nav.getByRole('button', { name: 'trace', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Trace path', exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
});
