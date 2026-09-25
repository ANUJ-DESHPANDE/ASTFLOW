/* Exhaustive runtime control crawl for the ASTFLOW audit.
 * For every UI state and viewport: inventory every visible interactive element, then (from a fresh load of that
 * state) interact with each one and record visible effect, console errors, failed requests and axe results.
 * Output: audit/evidence/ui-crawl.json (+ screenshots in audit/evidence/ui-crawl/).
 */
import { test, type Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import fs from 'node:fs';

type Control = { key: string; role: string; name: string; disabled: boolean; tag: string };
const OUT = 'audit/evidence/ui-crawl';
fs.mkdirSync(OUT, { recursive: true });

async function ready(page: Page) {
  await page.goto('/', { timeout: 30_000 });
  await page.locator('.monaco-editor').first().waitFor({ timeout: 30_000 });
  await page.waitForLoadState('networkidle', { timeout: 5_000 }).catch(() => {});
}
async function companion(page: Page) {
  // Below 850 px the companion is a drawer that starts closed; "Ask" opens it.
  if (!(await page.getByLabel('Ask about your code').isVisible())) await page.getByRole('button', { name: 'Ask', exact: true }).click();
}
async function settle(page: Page) {
  // The UI polls (index status 1 s, checkpoint 15 s), so network idle is best-effort only.
  await page.waitForLoadState('networkidle', { timeout: 3_000 }).catch(() => {});
  await page.waitForTimeout(400);
}

const states: Record<string, (page: Page) => Promise<void>> = {
  'code (initial)': async page => { await ready(page); },
  'code after search': async page => { await ready(page); await companion(page); await page.getByLabel('Ask about your code').fill('Where is Bluetooth settings handled?'); await page.getByLabel('Send question').click(); await page.locator('.source-matches button').first().waitFor(); await settle(page); },
  'code after structural search': async page => { await ready(page); await companion(page); await page.getByLabel('Ask about your code').fill('Does VoiceHandler call normalizeInput before IntentRouter?'); await page.getByLabel('Send question').click(); await page.locator('.conversation-turn').first().waitFor(); await settle(page); },
  'explorer filter open': async page => { await ready(page); await page.getByLabel('Filter files').click(); await settle(page); },
  'repository dialog': async page => { await ready(page); await page.getByLabel('Repository settings').click(); await page.getByRole('dialog').waitFor(); await settle(page); },
  'map overview': async page => { await ready(page); await page.getByRole('button', { name: 'Map', exact: true }).click(); await page.locator('.react-flow__node').first().waitFor(); await settle(page); },
  'map file focus': async page => { await ready(page); await page.getByRole('button', { name: 'Map', exact: true }).click(); await page.getByLabel('Map file focus').selectOption('voice/VoiceHandler.js'); await page.locator('.react-flow__node').first().waitFor(); await settle(page); },
  'map node selected': async page => { await ready(page); await page.getByRole('button', { name: 'Map', exact: true }).click(); await page.getByLabel('Map file focus').selectOption('voice/VoiceHandler.js'); await page.locator('.react-flow__node').first().click(); await page.locator('.graph-selection').waitFor(); await settle(page); },
  'trace mode': async page => { await ready(page); await page.getByRole('button', { name: 'Map', exact: true }).click(); await page.getByRole('button', { name: 'Trace a path' }).click(); await page.getByRole('button', { name: 'Trace', exact: true }).click(); await settle(page); },
  'compare (before run)': async page => { await ready(page); await page.getByRole('button', { name: 'Compare', exact: true }).first().click(); await settle(page); },
  'compare (after run)': async page => { await ready(page); await page.getByRole('button', { name: 'Compare', exact: true }).first().click(); await page.getByRole('main').getByRole('button', { name: 'Compare', exact: true }).click(); await page.locator('.monaco-diff-editor').waitFor(); await settle(page); },
};

async function inventory(page: Page): Promise<Control[]> {
  return page.evaluate(() => {
    const sel = 'button, a[href], input, select, textarea, summary, [role="button"], [role="tab"], [role="checkbox"], .react-flow__node, .react-flow__edge';
    const seen = new Map<string, number>();
    const out: Control[] = [];
    for (const el of Array.from(document.querySelectorAll<HTMLElement>(sel))) {
      const r = el.getBoundingClientRect(); const cs = getComputedStyle(el);
      if (!r.width || !r.height || cs.visibility === 'hidden' || cs.display === 'none') continue;
      if (el.closest('.monaco-editor') && el.tagName !== 'TEXTAREA') continue; // Monaco internals
      const tag = el.tagName.toLowerCase();
      const role = el.getAttribute('role') ?? (el.classList.contains('react-flow__node') ? 'graph-node' : el.classList.contains('react-flow__edge') ? 'graph-edge' : tag === 'a' ? 'link' : tag === 'select' ? 'combobox' : tag === 'input' ? ((el as HTMLInputElement).type === 'checkbox' ? 'checkbox' : 'textbox') : tag === 'textarea' ? 'textbox' : tag === 'summary' ? 'summary' : 'button');
      const labelled = el.getAttribute('aria-labelledby');
      const name = (el.getAttribute('aria-label') || (labelled && document.getElementById(labelled)?.textContent) || el.closest('label')?.textContent || el.textContent || el.getAttribute('title') || (el as HTMLInputElement).placeholder || '').replace(/\s+/g, ' ').trim().slice(0, 80);
      const base = `${role}|${name}`; const n = seen.get(base) ?? 0; seen.set(base, n + 1);
      out.push({ key: `${base}#${n}`, role, name, disabled: (el as HTMLButtonElement).disabled === true || el.getAttribute('aria-disabled') === 'true', tag });
    }
    return out;
  });
}

async function locate(page: Page, c: Control) {
  const [base, idx] = c.key.split('#');
  const all = await inventory(page);
  const pos = all.filter(x => x.key.split('#')[0] === base).findIndex(x => x.key === c.key);
  if (pos < 0) return null;
  const sel = 'button, a[href], input, select, textarea, summary, [role="button"], [role="tab"], [role="checkbox"], .react-flow__node, .react-flow__edge';
  const handles = await page.locator(sel).elementHandles();
  let k = 0;
  for (const h of handles) {
    const meta = await h.evaluate((el, [role, name]) => {
      const r = el.getBoundingClientRect(); const cs = getComputedStyle(el);
      if (!r.width || !r.height || cs.visibility === 'hidden' || cs.display === 'none') return false;
      if ((el as HTMLElement).closest('.monaco-editor') && el.tagName !== 'TEXTAREA') return false;
      const tag = el.tagName.toLowerCase();
      const rr = el.getAttribute('role') ?? (el.classList.contains('react-flow__node') ? 'graph-node' : el.classList.contains('react-flow__edge') ? 'graph-edge' : tag === 'a' ? 'link' : tag === 'select' ? 'combobox' : tag === 'input' ? ((el as HTMLInputElement).type === 'checkbox' ? 'checkbox' : 'textbox') : tag === 'textarea' ? 'textbox' : tag === 'summary' ? 'summary' : 'button');
      const labelled = el.getAttribute('aria-labelledby');
      const nm = (el.getAttribute('aria-label') || (labelled && document.getElementById(labelled)?.textContent) || el.closest('label')?.textContent || el.textContent || el.getAttribute('title') || (el as HTMLInputElement).placeholder || '').replace(/\s+/g, ' ').trim().slice(0, 80);
      return rr === role && nm === name;
    }, [c.role, c.name]);
    if (meta) { if (k === Number(idx)) return h; k++; }
  }
  return null;
}

async function signature(page: Page) {
  return page.evaluate(() => {
    const main = document.querySelector('main')?.textContent ?? '';
    const comp = document.querySelector('.companion')?.textContent ?? '';
    const cls = document.querySelector('.studio')?.className ?? '';
    const dialog = document.querySelectorAll('[role="dialog"]').length;
    const selected = Array.from(document.querySelectorAll('.selected, .active, [aria-selected="true"], [aria-expanded="true"], details[open]')).map(e => e.textContent?.slice(0, 30)).join('|');
    const inputs = Array.from(document.querySelectorAll<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>('input, select, textarea')).map(e => (e as HTMLInputElement).type === 'checkbox' ? String((e as HTMLInputElement).checked) : e.value).join('|');
    const flow = document.querySelector('.react-flow__viewport')?.getAttribute('style') ?? '';
    const monaco = Array.from(document.querySelectorAll('.monaco-editor .view-lines')).map(e => e.textContent?.slice(0, 200)).join('|');
    const zoom = document.querySelector('.monaco-editor')?.getAttribute('style') ?? '';
    return JSON.stringify({ url: location.href, main: main.length + ':' + main.slice(0, 400), comp: comp.length + ':' + comp.slice(-400), cls, dialog, selected, inputs, flow, monaco, zoom, fs: !!document.fullscreenElement, focus: document.activeElement?.getAttribute('aria-label') ?? document.activeElement?.tagName });
  });
}

const viewports = { desktop: { width: 1440, height: 1000 }, tablet: { width: 768, height: 1024 }, mobile: { width: 390, height: 844 } };
const perViewportStates: Record<string, string[]> = { desktop: Object.keys(states), tablet: ['code (initial)', 'code after search', 'map overview', 'compare (after run)', 'repository dialog'], mobile: ['code (initial)', 'code after search', 'map overview', 'compare (after run)', 'repository dialog'] };

test('exhaustive control crawl', async ({ page }) => {
  const results: any[] = []; const inventories: any = {}; const axe: any = {};
  const crawled = new Set<string>();
  for (const [vp, size] of Object.entries(viewports)) {
    await page.setViewportSize(size);
    for (const state of perViewportStates[vp]) {
      try { await states[state](page); } catch (e) { results.push({ viewport: vp, state, effect: 'STATE_SETUP_FAILED', error: (e as Error).message.split('\n')[0] }); continue; }
      await page.screenshot({ path: `${OUT}/${vp}-${state.replace(/[^a-z0-9]+/gi, '_')}.png` });
      const controls = await inventory(page);
      inventories[`${vp} / ${state}`] = controls;
      const scan = await new AxeBuilder({ page }).exclude('.monaco-editor').analyze();
      axe[`${vp} / ${state}`] = scan.violations.map(v => ({ id: v.id, impact: v.impact, help: v.help, nodes: v.nodes.length, targets: v.nodes.slice(0, 5).map(n => n.target.join(' ')) }));
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
      axe[`${vp} / ${state}`].push({ id: 'horizontal-overflow', impact: overflow ? 'serious' : 'none', help: 'Page wider than viewport', nodes: overflow ? 1 : 0 });
      for (const c of controls) {
        const dedupe = `${vp}|${c.key}`;
        if (crawled.has(dedupe)) continue;
        crawled.add(dedupe);
        const row: any = { viewport: vp, state, ...c, action: '', effect: '', console: [] as string[], failed: [] as string[] };
        console.log(`[${new Date().toISOString().slice(11, 19)}] ${vp} | ${state} | ${c.role} "${c.name}"`);
        if (c.disabled) { row.effect = 'DISABLED'; results.push(row); continue; }
        try { await states[state](page); } catch (e) { row.effect = 'STATE_SETUP_FAILED'; row.error = (e as Error).message.split('\n')[0]; results.push(row); continue; }
        const consoleErrors: string[] = []; const failed: string[] = [];
        const onConsole = (m: any) => { if (m.type() === 'error') consoleErrors.push(m.text().slice(0, 200)); };
        const onPageError = (e: Error) => consoleErrors.push('pageerror: ' + e.message.slice(0, 200));
        const onResponse = (r: any) => { if (r.status() >= 400) failed.push(`${r.status()} ${r.request().method()} ${r.url().replace(/^https?:\/\/[^/]+/, '')}`); };
        const onFailed = (r: any) => failed.push(`FAILED ${r.method()} ${r.url().replace(/^https?:\/\/[^/]+/, '')} ${r.failure()?.errorText}`);
        page.on('console', onConsole); page.on('pageerror', onPageError); page.on('response', onResponse); page.on('requestfailed', onFailed);
        try {
          let h = await locate(page, c);
          if (!h) {
            // Fallback: same role + name, first match (ranks/evidence text can differ only in whitespace/truncation).
            const byName = page.locator('button, a[href], input, select, textarea, summary, [role="button"], [role="checkbox"], .react-flow__node, .react-flow__edge')
              .filter({ hasText: c.name.slice(0, 30) });
            if (c.name && await byName.count()) { h = await byName.first().elementHandle(); row.relocated = 'by-name'; }
          }
          if (!h) { row.effect = 'NOT_FOUND_ON_RELOAD'; }
          else {
            // Reveal the control the way a user would: open collapsed <details> ancestors, scroll into view.
            await h.evaluate((el: Element) => { for (let d = el.closest('details'); d; d = d.parentElement?.closest('details') ?? null) (d as HTMLDetailsElement).open = true; el.scrollIntoView({ block: 'center' }); });
            await page.waitForTimeout(150);
            // If another element covers the control's centre, record which (a user could not click it either).
            const cover = await h.evaluate((el: Element) => { const r = el.getBoundingClientRect(); const top = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2); return !top || el.contains(top) || top.contains(el) ? '' : ((top.closest('aside, section, header, nav, main') as HTMLElement | null)?.className || top.tagName); });
            if (cover) row.coveredBy = cover;
            const before = await signature(page);
            if (c.role === 'combobox') {
              const opts = await h.evaluate((el: any) => Array.from(el.options).map((o: any) => ({ v: o.value, d: o.disabled, s: o.selected })));
              const next = opts.find((o: any) => !o.s && !o.d);
              row.action = next ? `select ${next.v}` : 'select (no alternative)';
              if (next) await h.selectOption(next.v);
            } else if (c.role === 'textbox' && c.tag !== 'button') {
              row.action = 'fill "Bluetooth"'; await h.fill('Bluetooth');
            } else if (c.role === 'checkbox') { row.action = 'toggle'; await h.click(); }
            else if (c.role === 'link') { row.action = 'click link'; await h.click(); }
            else { row.action = 'click'; await h.click({ timeout: 5000 }); }
            await settle(page);
            if (row.action.startsWith('fill') && c.name === 'Ask about your code') { /* follow-up covered by send */ }
            const after = await signature(page);
            row.effect = before === after ? 'NO_VISIBLE_CHANGE' : 'CHANGED';
            if (row.effect === 'NO_VISIBLE_CHANGE') await page.screenshot({ path: `${OUT}/nochange-${vp}-${results.length}.png` });
          }
        } catch (e) { row.effect = 'ERROR'; row.error = (e as Error).message.split('\n')[0].slice(0, 200); }
        page.off('console', onConsole); page.off('pageerror', onPageError); page.off('response', onResponse); page.off('requestfailed', onFailed);
        row.console = consoleErrors; row.failed = failed;
        results.push(row);
        if (page.url() !== 'http://127.0.0.1:8000/') await page.goto('/');
      }
      fs.writeFileSync('audit/evidence/ui-crawl.json', JSON.stringify({ results, inventories, axe, complete: false }, null, 1));
    }
  }
  fs.writeFileSync('audit/evidence/ui-crawl.json', JSON.stringify({ results, inventories, axe, complete: true }, null, 1));
});
