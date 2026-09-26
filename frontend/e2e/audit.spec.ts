import {test,expect} from '@playwright/test';
import {layoutGraph,neighborhood} from '../src/components/graphLayout';
import type {GraphData} from '../src/types';
import fs from 'node:fs';

test('positive sequence evidence opens real fixture source',async({page},testInfo)=>{
 const original=await (await page.request.get('/api/repository')).json();
 const repo=testInfo.outputPath('sequence-fixture');fs.mkdirSync(repo,{recursive:true});
 fs.writeFileSync(repo+'/sequence.js','function check(){} function open(){} function run(){check();open();}');
 try{
  expect((await page.request.post('/api/index',{data:{repo_path:repo,background:false}})).ok()).toBe(true);
  await page.goto('/');await expect(page.locator('.monaco-editor')).toBeVisible();
  await page.getByLabel('Ask about your code').fill('Which functions call check before open?');
  await page.getByLabel('Send question').click();
  await expect(page.locator('.sequence-evidence')).toContainText('Lexical order only');
  await page.locator('.sequence-evidence .source-link').click();
  await expect(page.locator('.source-status')).toContainText('sequence.js');
 }finally{
  for(const version of ['v1','v2','working-tree'])expect((await page.request.post('/api/index',{data:{repo_path:original.path,version,background:false}})).ok()).toBe(true);
 }
});

test('history restores comparison snapshots and source shortcuts remain functional',async({page,context})=>{
 await context.grantPermissions(['clipboard-read','clipboard-write']);
 await page.goto('/');await expect(page.locator('.monaco-editor')).toBeVisible();
 await page.locator('.folder-row').filter({hasText:'auth'}).click();
 await expect(page.getByTitle('auth/AuthService.js',{exact:true})).toHaveCount(0);
 await page.locator('.folder-row').filter({hasText:'auth'}).click();
 await page.getByLabel('Focus source context').click();
 await expect(page.getByLabel('Ask about your code')).toHaveValue('Where is AuthService used?');
 await page.getByLabel('Ask about your code').fill('');
 await page.getByLabel('Compare versions',{exact:true}).click();
 await page.getByLabel('Version A',{exact:true}).selectOption('v1');
 await page.getByLabel('Version B',{exact:true}).selectOption('v2');
 await page.getByRole('main').getByRole('button',{name:'Compare',exact:true}).click();
 await expect(page.locator('.monaco-diff-editor')).toBeVisible();
 await page.locator('.diff-evidence').getByLabel('Copy code').first().click();
 // Copy must yield exactly the "Before" snippet shown (the first modified symbol shared by both result lists).
 const shown=await page.locator('.diff-evidence .syntax-code').first().textContent();
 expect((await page.evaluate(()=>navigator.clipboard.readText())).replace(/\r\n/g,'\n')).toBe(shown); // Windows clipboard stores CRLF
 await page.getByLabel('Version A',{exact:true}).selectOption('v2');
 await page.getByLabel('Version B',{exact:true}).selectOption('v1');
 await page.getByRole('button',{name:'Inspect change',exact:true}).click();
 await expect(page.getByLabel('Version A',{exact:true})).toHaveValue('v1');
 await expect(page.getByLabel('Version B',{exact:true})).toHaveValue('v2');
 await expect(page.locator('.conversation-turn')).toHaveCount(1);
 await page.getByLabel('System map',{exact:true}).click();
 // The companion's Chat button focuses the composer (the old rail control labelled 'Source evidence' no longer exists).
 await page.locator('.companion-heading').getByRole('button',{name:'Chat'}).click();
 await expect(page.getByLabel('Ask about your code')).toBeFocused();
 await page.keyboard.press('Control+k');await expect(page.getByLabel('Ask about your code')).toBeFocused();
});
test('filter, clipboard, fullscreen, refinement setting and sequence evidence',async({page,context})=>{
 await context.grantPermissions(['clipboard-read','clipboard-write']);
 await page.goto('/');await expect(page.locator('.monaco-editor')).toBeVisible();
 await page.getByLabel('Filter files',{exact:true}).click();
 await page.getByLabel('Filter repository files').fill('VoiceHandler');
 await expect(page.locator('.file-row')).toHaveCount(1);
 await page.getByLabel('Filter repository files').fill('nothing-with-this-name');
 await expect(page.locator('.file-row')).toHaveCount(0);
 await page.getByLabel('Filter repository files').fill('');
 await page.getByLabel('Copy selected source').click();
 expect(await page.evaluate(()=>navigator.clipboard.readText())).toContain('AuthService');
 await page.getByLabel('Expand workspace').click();
 await expect.poll(()=>page.evaluate(()=>Boolean(document.fullscreenElement))).toBe(true);
 await page.getByLabel('Expand workspace').click();
 await expect.poll(()=>page.evaluate(()=>Boolean(document.fullscreenElement))).toBe(false);
 await page.getByText('How this works',{exact:false}).click();
 await page.getByLabel('Allow one retrieval refinement').uncheck();
 const request=page.waitForRequest(r=>r.url().endsWith('/api/search'));
 await page.getByLabel('Ask about your code').fill('checkBluetoothPermission before openBluetoothSettings');
 await page.getByLabel('Send question').click();expect((await request).postDataJSON().agentic).toBe(false);
 // BluetoothAgent.execute: `checkBluetoothPermission(); return openBluetoothSettings();`. A final return cannot skip
 // the statement before it, so the pair is supported (early exits in between are still rejected: test_regressions.py).
 await expect(page.locator('.sequence-evidence')).toContainText('checkBluetoothPermission → openBluetoothSettings');
 await expect(page.locator('.sequence-evidence')).toContainText('bluetooth/BluetoothAgent.js:7–8');
});
test('startup selects the indexed commit when working tree is not indexed',async({page})=>{
 await page.route('**/api/repository?version=working-tree',async route=>{
  const response=await route.fetch();const data=await response.json();
  data.indexes=data.indexes.filter((entry:{version:string})=>entry.version==='v1');data.files=[];
  await route.fulfill({response,json:data});
 });
 await page.goto('/');await expect(page.getByLabel('Repository version')).toHaveValue('v1');
 await expect(page.locator('.monaco-editor')).toBeVisible();
 await expect(page.getByTitle('voice/VoiceHandler.js',{exact:true})).toBeVisible();
});
function graph(count:number,pairs:number[][]):GraphData{return {nodes:Array.from({length:count},(_,i)=>({symbol_id:String(i).padStart(4,'0'),qualified_name:`node${i}`,file:'test.js',start_line:1,end_line:1,kind:'function'})),edges:pairs.map(([a,b])=>({source:String(a).padStart(4,'0'),target:String(b).padStart(4,'0'),call_file:'test.js',call_line:1,call_end_line:1,source_expression:'f()',resolution_method:'lexical_scope',evidence_type:'STATIC_VERIFIED',evidence_sources:[]})),paths:[]};}
for(const [label,count,pairs] of [['small',4,[[0,1],[1,2]]],['medium',80,Array.from({length:79},(_,i)=>[i,i+1])],['large',1000,Array.from({length:999},(_,i)=>[i,i+1])],['dense',30,Array.from({length:30},(_,a)=>Array.from({length:30},(_,b)=>[a,b])).flat()],['disconnected',100,[[0,1],[2,3]]]] as [string,number,number[][]][]){
 test(`layout ${label}: stable under reversed traversal, no node overlap`,()=>{const g=graph(count,pairs),a=layoutGraph(g),b=layoutGraph({...g,nodes:[...g.nodes].reverse(),edges:[...g.edges].reverse()});expect([...a].sort()).toEqual([...b].sort());expect(new Set([...a.values()].map(p=>`${p.x}:${p.y}`)).size).toBe(count);for(const p of a.values()){expect(Number.isFinite(p.x)&&Number.isFinite(p.y)).toBeTruthy();}if(label!=='dense')for(const e of g.edges)expect(a.get(e.source)!.y).toBeLessThan(a.get(e.target)!.y);});}
test('neighborhood respects incoming/outgoing/depth',()=>{const g=graph(5,[[0,1],[1,2],[2,3]]);expect([...neighborhood(g,'0001',1,'incoming')].sort()).toEqual(['0000','0001']);expect([...neighborhood(g,'0001',2,'outgoing')].sort()).toEqual(['0001','0002','0003']);});
test('real graph node search, neighborhood selection and source navigation',async({page})=>{await page.goto('/');await expect(page.locator('.monaco-editor')).toBeVisible();await page.getByRole('button',{name:'Map',exact:true}).click();await page.getByLabel('Map file focus').selectOption('voice/VoiceHandler.js');await page.getByLabel('Search graph nodes').fill('handleRequest');await page.locator('.graph-matches button').first().click();await expect(page.locator('.graph-selection')).toContainText('VoiceHandler.handleRequest');await page.getByRole('button',{name:'Hide unrelated'}).click();await page.getByLabel('Neighborhood depth').selectOption('2');await page.getByLabel('Call direction').selectOption('outgoing');await page.getByLabel('Fit graph').click();await page.getByRole('button',{name:'Explore calls',exact:true}).click();await expect(page.locator('.canvas-caption')).toContainText('call hop');await page.getByLabel('Fit graph').click();await expect.poll(async()=>page.locator('.react-flow__viewport').evaluate(e=>Number(getComputedStyle(e).transform.split(',')[0].replace('matrix(','')))).toBeLessThan(1);await page.screenshot({path:'.astflow/screenshots/audit-graph.png'});await page.getByLabel('Reset graph').click();await expect(page.locator('.graph-selection')).toHaveCount(0);});
test('API network failure, malformed reply, empty search and recovery',async({page})=>{await page.goto('/');await expect(page.locator('.monaco-editor')).toBeVisible();await page.route('**/api/search',route=>route.abort('failed'));await page.getByLabel('Ask about your code').fill('Bluetooth');await page.getByLabel('Send question').click();await expect(page.locator('.error-notice[role=alert]')).toContainText('Cannot reach ASTFLOW');await page.unroute('**/api/search');await page.getByLabel('Dismiss error').click();await page.route('**/api/search',route=>route.fulfill({status:502,contentType:'text/html',body:'<h1>Bad Gateway</h1>'}));await page.getByLabel('Ask about your code').fill('Bluetooth');await page.getByLabel('Send question').click();await expect(page.locator('.error-notice[role=alert]')).toContainText('invalid response');await page.unroute('**/api/search');await page.getByLabel('Ask about your code').fill('qxzjvnonexistentidentifier');await page.getByLabel('Send question').click();await expect(page.locator('.conversation-turn').last().locator('h3')).toHaveText('Closest matches by meaning');});
