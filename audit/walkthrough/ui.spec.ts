/* The judge walkthrough through the real UI. Screenshots and observed facts go to audit/walkthrough/. */
import { test, expect, type Page } from '@playwright/test';
import fs from 'node:fs';

const OUT = 'audit/walkthrough';
const facts: Record<string, unknown> = {};
const consoleErrors: string[] = [];
const shot = (page: Page, name: string) => page.screenshot({ path: `${OUT}/screens/${name}.png` });

async function ask(page: Page, question: string) {
  const box = page.getByLabel('Ask about your code');
  if (!(await box.isVisible())) await page.getByRole('button', { name: 'Ask', exact: true }).click();
  await box.fill(question);
  const started = Date.now();
  await page.getByLabel('Send question').click();
  const turn = page.locator('.conversation-turn').last();
  await expect(turn.locator('h3')).toBeVisible({ timeout: 120_000 });
  const uiMs = Date.now() - started;
  await page.waitForTimeout(1000);  // the companion scrolls smoothly to the new answer
  return { turn, uiMs };
}

test.beforeEach(({ page }) => {
  page.on('console', m => { if (m.type() === 'error') consoleErrors.push(m.text()); });
  page.on('pageerror', e => consoleErrors.push(String(e)));
});
test.afterAll(() => {
  fs.writeFileSync(`${OUT}/ui.json`, JSON.stringify({ ...facts, console_errors: consoleErrors }, null, 1));
});

test('express: configuration, plain-English query, version switching, navigation', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByLabel('Ask about your code')).toBeVisible();
  await page.getByText('How this works', { exact: false }).click();
  facts.retrieval_config_shown = await page.locator('.retrieval-config').innerText();
  await shot(page, '01-express-open-config');

  const markers: Record<string, string> = { '4.18.2': 'var loc = url;', '4.19.2': 'schemaAndHostRegExp', '4.21.2': 'security-redirect' };
  const versions: Record<string, unknown> = {};
  for (const version of Object.keys(markers)) {
    await page.getByLabel('Repository version', { exact: true }).selectOption(version);
    const { turn, uiMs } = await ask(page, 'where is the redirect location URL encoded');
    const first = turn.locator('.source-matches button').first();
    const label = await first.innerText();
    await first.click();
    await expect(page.locator('.source-status')).toContainText('lib/response.js');
    const lines = await page.locator('.monaco-editor .view-lines').innerText();
    versions[version] = { top_result: label, ui_ms: uiMs, selector: await page.getByLabel('Repository version', { exact: true }).inputValue(),
      source_status: await page.locator('.source-status').innerText(), shows_version_specific_source: lines.includes(markers[version]) };
    await shot(page, `02-express-${version}-location`);
  }
  facts.version_journey = versions;

  const t1 = await ask(page, 'Which code picks the response format based on what the client says it accepts?');
  facts.t1 = { heading: await t1.turn.locator('h3').innerText(), top: await t1.turn.locator('.source-matches button').first().innerText(), ui_ms: t1.uiMs };
  await t1.turn.locator('.source-matches button').first().click();
  await shot(page, '03-express-plain-english');

  const t5 = await ask(page, 'Where is view template rendering implemented?');
  facts.t5 = { top3: await t5.turn.locator('.source-matches button').evaluateAll(b => b.slice(0, 3).map(x => (x as HTMLElement).innerText)), ui_ms: t5.uiMs };
  await t5.turn.locator('.source-matches button').first().click();
  await shot(page, '04-express-large-repo-result');
  await page.getByRole('navigation', { name: 'Workspace views' }).getByRole('button', { name: 'Map', exact: true }).click();
  await expect(page.locator('.canvas-caption')).toBeVisible();
  facts.express_map_caption = await page.locator('.canvas-caption').innerText();
  await shot(page, '05-express-map');

  const t6 = await ask(page, 'Where is the Kafka consumer offset committed?');
  facts.t6 = { heading: await t6.turn.locator('h3').innerText(), text: (await t6.turn.innerText()).slice(0, 400) };
  await shot(page, '06-express-no-evidence');
});

test('demo: usage, call order, graph trace', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByLabel('Ask about your code')).toBeVisible();
  await expect(page.getByLabel('Repository version', { exact: true })).toBeEnabled();
  await page.getByLabel('Repository settings').click();
  await expect(page.getByRole('button', { name: 'Use demo repository' })).toBeEnabled();
  await page.getByRole('button', { name: 'Use demo repository' }).click();
  await page.getByRole('button', { name: 'Open & index' }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(page.locator('.source-panel')).toBeVisible({ timeout: 300_000 });

  const usage = await ask(page, 'Where is openBluetoothSettings used?');
  facts.t2_demo = { top3: await usage.turn.locator('.source-matches button').evaluateAll(b => b.slice(0, 3).map(x => (x as HTMLElement).innerText)) };
  await shot(page, '07-demo-usage');

  const order = await ask(page, 'Which functions call checkBluetoothPermission before openBluetoothSettings?');
  facts.t3 = { sequence_evidence: await order.turn.locator('.sequence-evidence').innerText().catch(() => 'NONE') };
  await shot(page, '08-demo-call-order');

  await page.getByRole('navigation', { name: 'Workspace views' }).getByRole('button', { name: 'Map', exact: true }).click();
  await page.getByRole('button', { name: 'Trace a path' }).click();
  await page.getByRole('button', { name: 'Trace', exact: true }).click();
  await expect(page.locator('.canvas-caption')).toContainText('supported path');
  facts.t7_trace_caption = await page.locator('.canvas-caption').innerText();
  const edge = await page.locator('.react-flow__edge-path').first().evaluate((path: SVGPathElement) => {
    const p = path.getPointAtLength(path.getTotalLength() / 2).matrixTransform(path.getScreenCTM()!); return { x: p.x, y: p.y }; });
  await page.mouse.click(edge.x, edge.y);
  await expect(page.locator('.edge-evidence')).toBeVisible();
  facts.t7_edge_evidence = (await page.locator('.edge-evidence').innerText()).slice(0, 300);
  await shot(page, '09-demo-trace-edge');
  expect(consoleErrors).toEqual([]);
});
