import { useEffect, useRef } from 'react';
import Editor, { loader } from '@monaco-editor/react';
import type { OnMount } from '@monaco-editor/react';
import * as monaco from 'monaco-editor/esm/vs/editor/editor.api.js';
import 'monaco-editor/esm/vs/basic-languages/javascript/javascript.contribution.js';
import EditorWorker from 'monaco-editor/esm/vs/editor/editor.worker.js?worker';
import { ArrowLeft, Check, Copy, FileCode2 } from 'lucide-react';
import { useState } from 'react';
import type { Source } from '../types';

self.MonacoEnvironment = { getWorker: () => new EditorWorker() };
loader.config({ monaco });

export function SourceViewer({ source, onClose }: { source: Source; onClose: () => void }) {
  const editor = useRef<monaco.editor.IStandaloneCodeEditor | null>(null);
  const decorations = useRef<monaco.editor.IEditorDecorationsCollection | null>(null);
  const [copied, setCopied] = useState(false);
  const highlight = () => {
    decorations.current?.clear();
    decorations.current = editor.current?.createDecorationsCollection([{
      range: new monaco.Range(source.start_line, 1, source.end_line, 1),
      options: { isWholeLine: true, className: 'source-highlight', linesDecorationsClassName: 'source-gutter-highlight' },
    }]) ?? null;
    editor.current?.revealLineInCenter(source.start_line);
  };
  const mount: OnMount = instance => { editor.current = instance; highlight(); };
  useEffect(() => { const timer = setTimeout(highlight, 30); return () => clearTimeout(timer); }, [source]);
  async function copy() {
    try { await navigator.clipboard.writeText(source.content); setCopied(true); setTimeout(() => setCopied(false), 1500); }
    catch { setCopied(false); }
  }
  return <section className="source-panel" aria-label="Source viewer">
    <div className="source-toolbar"><button className="icon-button" onClick={onClose} aria-label="Back to results"><ArrowLeft size={17}/></button>
      <FileCode2 size={16} className="accent"/><span className="mono truncate">{source.path}</span>
      <button className="icon-button push-right" onClick={copy} aria-label="Copy selected source">{copied ? <Check size={16}/> : <Copy size={16}/>}</button></div>
    <div className="source-location"><span>INDEXED SOURCE</span><span className="mono">L{source.start_line}–{source.end_line} · {source.version_key.slice(0, 8)}</span></div>
    <Editor height="100%" language="javascript" value={source.full_content} path={`${source.version_key}/${source.path}`} theme="vs-dark" onMount={mount}
      options={{ readOnly: true, domReadOnly: true, minimap: { enabled: false }, fontSize: 13, lineHeight: 23,
        fontFamily: 'Cascadia Code, Consolas, monospace', scrollBeyondLastLine: false, padding: { top: 18 },
        wordWrap: 'on', renderLineHighlight: 'none', automaticLayout: true, overviewRulerLanes: 0, folding: true }}/>
  </section>;
}
