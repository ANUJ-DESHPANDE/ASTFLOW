import {test,expect} from '@playwright/test';
import fs from 'node:fs';
fs.mkdirSync('.astflow/screenshots',{recursive:true});
async function opened(page:any){await page.goto('/');await expect(page.locator('.monaco-editor')).toBeVisible();}
test('reference shell, real file tabs, zoom and closing tabs',async({page})=>{
 const errors:string[]=[];page.on('pageerror',e=>errors.push(e.message));await opened(page);
 await expect(page.locator('.source-status')).toContainText('auth/AuthService.js');
 await page.getByTitle('voice/VoiceHandler.js',{exact:true}).click();
 const openFiles=page.getByRole('group',{name:'Open source files'});await expect(openFiles.getByRole('button',{name:'JS VoiceHandler.js'})).toHaveAttribute('aria-current','true');
 await openFiles.getByRole('button',{name:'JS AuthService.js'}).click();await expect(page.locator('.source-status')).toContainText('auth/AuthService.js');
 await page.getByLabel('Editor zoom').selectOption('125');await expect(page.getByLabel('Editor zoom')).toHaveValue('125');
 await page.getByLabel('Close auth/AuthService.js',{exact:true}).click();await expect(page.locator('.source-status')).toContainText('voice/VoiceHandler.js');
 await page.getByLabel('Editor zoom').selectOption('100');await page.screenshot({path:'.astflow/screenshots/studio-code.png'});await page.getByRole('button',{name:'Ask',exact:true}).click();await expect(page.locator('.companion')).not.toBeVisible();await page.getByRole('button',{name:'Ask',exact:true}).click();await expect(page.locator('.companion')).toBeVisible();await page.getByRole('button',{name:'Explorer',exact:true}).click();await expect(page.locator('.explorer')).not.toBeVisible();expect(errors).toEqual([]);
});
test('live question shows real loading, evidence and exact source',async({page})=>{
 await opened(page);let release!:()=>void;const gate=new Promise<void>(r=>release=r);
 await page.route('**/api/search',async route=>{const response=await route.fetch();await gate;await route.fulfill({response});});
 await page.getByLabel('Ask about your code').fill('Where is session restoration handled?');await page.getByLabel('Send question').click();
 await expect(page.getByRole('status')).toContainText('Analyzing your code');await page.screenshot({path:'.astflow/screenshots/studio-loading.png'});release();
 await expect(page.locator('.source-matches button').first()).toBeVisible();await expect(page.locator('.user-message')).toContainText('session restoration');
 await page.locator('.source-matches button').first().click();await expect(page.locator('.source-status')).toContainText('session/SessionManager.js');
 await page.screenshot({path:'.astflow/screenshots/studio-search.png'});
});
test('map file focus and trace evidence navigate to code',async({page})=>{
 await opened(page);await page.getByRole('button',{name:'Map',exact:true}).click();await expect(page.locator('.react-flow__node').first()).toBeVisible();await page.screenshot({path:'.astflow/screenshots/studio-map.png'});
 await page.getByLabel('Map file focus').selectOption('voice/VoiceHandler.js');await page.locator('.react-flow__node').filter({hasText:'VoiceHandler.handleRequest'}).click();await page.getByRole('button',{name:'Open source',exact:true}).click();await expect(page.locator('.source-status')).toContainText('voice/VoiceHandler.js');
 await page.getByRole('button',{name:'Map',exact:true}).click();await page.getByRole('button',{name:'Trace a path'}).click();await page.getByRole('button',{name:'Trace',exact:true}).click();await expect(page.locator('.canvas-caption')).toContainText('supported path');
 await page.locator('.react-flow__edge').first().click({force:true});await expect(page.locator('.edge-evidence')).toContainText('A supported connection');await expect(page.locator('.source-panel')).toBeVisible();
});
test('comparison displays actual before and after source',async({page})=>{
 await opened(page);await page.getByRole('navigation',{name:'Workspace views'}).getByRole('button',{name:'Compare',exact:true}).click();await page.getByLabel('Version A',{exact:true}).selectOption('v1');await page.getByLabel('Version B',{exact:true}).selectOption('v2');await page.getByRole('main').getByRole('button',{name:'Compare',exact:true}).click();
 await expect(page.getByRole('region',{name:'Source comparison'})).toBeVisible();await expect(page.locator('.monaco-diff-editor')).toBeVisible();await expect(page.locator('.conversation')).toContainText('symbols modified');await expect(page.locator('.diff-evidence .syntax-code')).toHaveCount(2);await expect(page.locator('.error-notice')).toHaveCount(0);await page.screenshot({path:'.astflow/screenshots/studio-compare.png'});
});
test('late search cannot overwrite a newly selected snapshot',async({page})=>{
 await opened(page);let release!:()=>void;const gate=new Promise<void>(r=>release=r);let started!:()=>void;const requested=new Promise<void>(r=>started=r);
 await page.route('**/api/search',async route=>{const response=await route.fetch();started();await gate;await route.fulfill({response});});await page.getByLabel('Ask about your code').fill('Bluetooth');await page.getByLabel('Send question').click();await requested;
 await page.getByLabel('Repository version',{exact:true}).selectOption('v1');release();await page.getByTitle('auth/AuthService.js',{exact:true}).click();await expect(page.locator('.source-status')).toContainText('auth/AuthService.js');await expect(page.getByLabel('Repository version',{exact:true})).toHaveValue('v1');await expect(page.locator('.conversation-turn')).toHaveCount(0);
});
test('mobile drawers, escape, reduced motion and no overflow',async({page})=>{
 await page.setViewportSize({width:390,height:844});await page.emulateMedia({reducedMotion:'reduce'});await opened(page);await page.getByRole('button',{name:'Ask',exact:true}).click();await expect(page.getByLabel('Ask about your code')).toBeVisible();await page.screenshot({path:'.astflow/screenshots/studio-mobile.png'});await page.keyboard.press('Escape');await expect(page.locator('.companion')).not.toBeVisible();await expect(page.locator('.monaco-editor')).toBeVisible();await page.getByRole('button',{name:'Explorer',exact:true}).click();await expect(page.locator('.explorer')).toBeVisible();await page.keyboard.press('Escape');await expect(page.locator('.explorer')).not.toBeVisible();expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
});
test('repository dialog traps focus and closes without losing source',async({page})=>{
 await opened(page);await page.getByLabel('Repository settings').click();await expect(page.getByRole('dialog')).toBeVisible();await page.getByRole('button',{name:'Use demo repository'}).focus();await page.keyboard.press('Tab');await expect(page.getByLabel('Close dialog')).toBeFocused();await page.keyboard.press('Escape');await expect(page.getByRole('dialog')).toHaveCount(0);await expect(page.locator('.monaco-editor')).toBeVisible();
});
test('reindex completes with a live source editor',async({page})=>{
 await opened(page);const response=page.waitForResponse(r=>r.url().endsWith('/api/index')&&r.request().method()==='POST');await page.getByLabel('Reindex repository',{exact:true}).click();expect((await response).ok()).toBeTruthy();await expect(page.locator('.source-panel')).toBeVisible();await expect(page.locator('.error-notice')).toHaveCount(0);
});
