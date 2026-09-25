/* Diagnose missing trace edges after Map -> Open source -> Map -> Trace (audit only). */
import { test, expect } from '@playwright/test';

test('trace after open-source renders its edges', async ({ page }) => {
  const rows: string[] = [];
  for (let i = 0; i < 16; i++) {
    await page.goto('/'); await expect(page.locator('.monaco-editor')).toBeVisible();
    await page.getByRole('button', { name: 'Map', exact: true }).click();
    await expect(page.locator('.react-flow__node').first()).toBeVisible();
    await page.getByLabel('Map file focus').selectOption('voice/VoiceHandler.js');
    await page.locator('.react-flow__node').filter({ hasText: 'VoiceHandler.handleRequest' }).click();
    await page.getByRole('button', { name: 'Open source', exact: true }).click();
    await expect(page.locator('.source-status')).toContainText('voice/VoiceHandler.js');
    await page.getByRole('button', { name: 'Map', exact: true }).click();
    await page.getByRole('button', { name: 'Trace a path' }).click();
    await page.getByRole('button', { name: 'Trace', exact: true }).click();
    await expect(page.locator('.canvas-caption')).toContainText('supported path');
    const t0 = Date.now(); let edges = 0;
    while (Date.now() - t0 < 4000) { edges = await page.locator('.react-flow__edge').count(); if (edges) break; await page.waitForTimeout(100); }
    const state = await page.evaluate(() => ({
      nodes: document.querySelectorAll('.react-flow__node').length,
      edgePaths: document.querySelectorAll('.react-flow__edge-path').length,
      edgeSvg: document.querySelectorAll('.react-flow__edges svg').length,
      key: document.querySelector('.graph-key')?.textContent?.replace('Caller → callee · green: outgoing · gold: incoming', '').slice(0, 40),
      nodeIds: Array.from(document.querySelectorAll('.react-flow__node')).map(n => n.getAttribute('data-id')?.split('::')[1]).join(','),
    }));
    rows.push(`${i}: edges=${edges} ${JSON.stringify(state)}`);
  }
  console.log(rows.join('\n'));
});
