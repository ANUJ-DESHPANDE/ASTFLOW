import { useEffect, useRef } from 'react';
import Editor, { DiffEditor, loader } from '@monaco-editor/react';
import * as monaco from 'monaco-editor/esm/vs/editor/editor.api.js';
import 'monaco-editor/esm/vs/basic-languages/javascript/javascript.contribution.js';
import EditorWorker from 'monaco-editor/esm/vs/editor/editor.worker.js?worker';
import type { Source } from '../types';
self.MonacoEnvironment = { getWorker: () => new EditorWorker() };
// Switching or closing a tab disposes a model while Monaco still has cancellable work in flight; Monaco rejects
// those promises with its own CancellationError ("Canceled") and nothing awaits them. Swallow only that error.
window.addEventListener('unhandledrejection', event => {
  const reason = event.reason as { name?: string; message?: string } | undefined;
  if (reason?.name === 'Canceled' && reason.message === 'Canceled') event.preventDefault();
});
loader.config({ monaco });
function theme(api: typeof monaco) {
  api.editor.defineTheme('astflow', { base: 'vs-dark', inherit: true,
    rules: [{ token: 'keyword', foreground: 'BD79CF' }, { token: 'string', foreground: 'FF9A50' }, { token: 'comment', foreground: '719878' }, { token: 'identifier', foreground: '85C982' }, { token: 'number', foreground: 'E4AF63' }],
    colors: { 'editor.background': '#161616', 'editor.foreground': '#DDDDDF', 'editorLineNumber.foreground': '#878B85', 'editor.selectionBackground': '#285D36', 'diffEditor.insertedLineBackground': '#285E321F', 'diffEditor.removedLineBackground': '#7737371F', 'diffEditor.insertedTextBackground': '#285E321C', 'diffEditor.removedTextBackground': '#7737372A' } });
}
const options = (zoom: number): monaco.editor.IStandaloneEditorConstructionOptions => ({ readOnly: true, domReadOnly: true, minimap: { enabled: false }, fontSize: 15 * zoom / 100, lineHeight: 24 * zoom / 100, fontFamily: 'Cascadia Code, Consolas, monospace', scrollBeyondLastLine: false, padding: { top: 16 }, wordWrap: 'on', renderLineHighlight: 'none', automaticLayout: true, overviewRulerLanes: 0, folding: true });
export function SourceViewer({ source, zoom = 100 }: { source: Source; zoom?: number }) {
  const editor = useRef<monaco.editor.IStandaloneCodeEditor | null>(null);
  const decoration = useRef<monaco.editor.IEditorDecorationsCollection | null>(null);
  function highlight() { decoration.current?.clear(); if (source.start_line === 1 && source.end_line >= source.total_lines) return; decoration.current = editor.current?.createDecorationsCollection([{ range: new monaco.Range(source.start_line,1,source.end_line,1), options: { isWholeLine:true, className: 'source-highlight' } }]) ?? null; editor.current?.revealLineInCenter(source.start_line); }
  useEffect(() => { const timer=setTimeout(highlight,30);return()=>clearTimeout(timer); },[source]);
  return <section className="source-panel" aria-label="Source viewer"><Editor height="100%" language="javascript" value={source.full_content} path={`${source.version_key}/${source.path}`} theme="astflow" beforeMount={theme} onMount={instance=>{editor.current=instance;highlight();}} options={{...options(zoom),ariaLabel:`Source of ${source.path}, read only`}}/><footer className="source-status"><span>{source.path}</span><span>Read only · L{source.start_line}–{source.end_line} · {source.version_key.slice(0,8)}</span></footer></section>;
}
export function SourceDiff({ before, after, zoom=100 }: {before:Source;after:Source;zoom?:number}) {
 return <section className="source-panel" aria-label="Source comparison"><div className="diff-labels"><span><i/>Before · {before.version_key.slice(0,8)}</span><span><i/>After · {after.version_key.slice(0,8)}</span></div><DiffEditor height="100%" language="javascript" original={before.full_content} modified={after.full_content} originalModelPath={`before/${before.version_key}/${before.path}`} modifiedModelPath={`after/${after.version_key}/${after.path}`} theme="astflow" beforeMount={theme} keepCurrentOriginalModel keepCurrentModifiedModel onMount={diff=>{
   // The diff editor does not pass original/modifiedAriaLabel to its inner editors' input elements; label them directly.
   diff.getOriginalEditor().updateOptions({ariaLabel:`Before: ${before.path} (${before.version_key.slice(0,8)}), read only`});
   diff.getModifiedEditor().updateOptions({ariaLabel:`After: ${after.path} (${after.version_key.slice(0,8)}), read only`});
 }} options={{...options(zoom),renderSideBySide:true,enableSplitViewResizing:true,originalEditable:false,originalAriaLabel:`Before: ${before.path} (${before.version_key.slice(0,8)}), read only`,modifiedAriaLabel:`After: ${after.path} (${after.version_key.slice(0,8)}), read only`}}/><footer className="source-status"><span>{after.path}</span><span>Indexed source · read only</span></footer></section>;
}
