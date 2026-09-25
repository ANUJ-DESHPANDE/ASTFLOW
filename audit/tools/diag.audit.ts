/* Targeted reproductions of crawl rows that ended in ERROR / NOT_FOUND (audit only). */
import { test, expect, type Page } from '@playwright/test';

async function ready(page: Page) { await page.goto('/'); await expect(page.locator('.monaco-editor').first()).toBeVisible(); }
async function ask(page: Page, q: string) {
  if (!(await page.getByLabel('Ask about your code').isVisible())) await page.getByRole('button', { name: /^(Explain|Ask)$/ }).click();
  await page.getByLabel('Ask about your code').fill(q); await page.getByLabel('Send question').click();
  await expect(page.locator('.source-matches button').first()).toBeVisible();
}
async function tryClick(page: Page, label: string, locator: ReturnType<Page['locator']>) {
  try { await locator.click({ timeout: 4000 }); console.log(`OK   ${label}`); }
  catch (e) { console.log(`FAIL ${label}: ${(e as Error).message.split('\n').filter(l => /intercepts|not visible|outside|detached|Timeout/.test(l)).slice(0, 3).join(' | ')}`); }
}

test('diagnose', async ({ page }) => {
  for (const [vp, size] of Object.entries({ desktop: { width: 1440, height: 1000 }, tablet: { width: 768, height: 1024 }, mobile: { width: 390, height: 844 } })) {
    await page.setViewportSize(size);
    await ready(page); await ask(page, 'Where is Bluetooth settings handled?');
    const first = await page.locator('.source-matches button').allTextContents();
    await ready(page); await ask(page, 'Where is Bluetooth settings handled?');
    const second = await page.locator('.source-matches button').allTextContents();
    console.log(`${vp}: result buttons identical after reload: ${JSON.stringify(first) === JSON.stringify(second)} (${first.length})`);
    await page.locator('.assistant-message.introduction summary').click();
    await tryClick(page, `${vp} refinement checkbox`, page.getByLabel('Allow one retrieval refinement'));
    const unresolved = page.locator('.unresolved-note');
    if (await unresolved.count()) {
      await unresolved.locator('summary').click();
      await tryClick(page, `${vp} last unresolved-call link`, unresolved.locator('button.source-link').last());
    }
    await tryClick(page, `${vp} close deeplinks tab`, page.getByLabel('Close settings/deeplinks.js'));
    await ready(page);
    await page.getByRole('navigation', { name: 'Workspace views' }).getByRole('button', { name: 'Compare', exact: true }).click();
    await page.getByRole('main').getByRole('button', { name: 'Compare', exact: true }).click();
    await expect(page.locator('.monaco-diff-editor')).toBeVisible();
    await tryClick(page, `${vp} main Compare button (second run)`, page.getByRole('main').getByRole('button', { name: 'Compare', exact: true }));
    await page.screenshot({ path: `audit/evidence/ui-crawl/diag-${vp}-compare.png` });
  }
});
