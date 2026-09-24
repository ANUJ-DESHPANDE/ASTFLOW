/* Accessibility gate: no serious or critical axe (WCAG 2.x A/AA) violations in the main views, Monaco included. */
import { test, expect, type Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

async function opened(page: Page) { await page.goto('/'); await expect(page.locator('.monaco-editor')).toBeVisible(); }
async function scan(page: Page, view: string) {
  const { violations } = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'best-practice']).analyze();
  const blocking = violations.filter(v => v.impact === 'serious' || v.impact === 'critical');
  expect(blocking.map(v => `${view}: ${v.id} (${v.impact}) ${v.nodes.map(n => n.target.join(' ')).slice(0, 3).join(', ')}`)).toEqual([]);
}

for (const [label, size] of [['desktop', { width: 1440, height: 1000 }], ['mobile', { width: 390, height: 844 }]] as const) {
  test(`${label}: code, answer, map, compare and dialog have no serious/critical violations`, async ({ page }) => {
    await page.setViewportSize(size);
    await page.emulateMedia({ reducedMotion: 'reduce' }); // scan settled layouts, not drawer transitions
    await opened(page);
    await scan(page, 'code');
    if (!(await page.getByLabel('Ask about your code').isVisible())) await page.getByRole('button', { name: 'Ask', exact: true }).click();
    await page.getByLabel('Ask about your code').fill('Where is Bluetooth settings handled?');
    await page.getByLabel('Send question').click();
    await expect(page.locator('.source-matches button').first()).toBeVisible();
    await scan(page, 'answer');
    await page.goto('/'); await expect(page.locator('.monaco-editor')).toBeVisible();
    await page.getByRole('navigation', { name: 'Workspace views' }).getByRole('button', { name: 'Map', exact: true }).click();
    await expect(page.locator('.react-flow__node').first()).toBeVisible();
    await scan(page, 'map');
    await page.getByRole('navigation', { name: 'Workspace views' }).getByRole('button', { name: 'Compare', exact: true }).click();
    await page.getByRole('main').getByRole('button', { name: 'Compare', exact: true }).click();
    await expect(page.locator('.monaco-diff-editor')).toBeVisible();
    await scan(page, 'compare');
    await page.getByLabel('Repository settings').click();
    await expect(page.getByRole('dialog')).toBeVisible();
    await scan(page, 'dialog');
  });
}
