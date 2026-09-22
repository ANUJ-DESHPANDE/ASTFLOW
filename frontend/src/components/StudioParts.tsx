import { useState } from 'react';
import { Check, Copy } from 'lucide-react';

export function FlowMark({ loading = false }: { loading?: boolean }) {
  return <span aria-hidden="true" className={`flow-mark ${loading ? 'turning' : ''}`}>{Array.from({ length: 14 }, (_, i) => <i key={i} style={{ transform: `rotate(${i * 360 / 14}deg)`, background: i < 7 ? '#0da981' : '#347bdb' }}/>)}</span>;
}
export function CodeSnippet({ text }: { text: string }) {
  const tokens = text.split(/("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|\b(?:export|import|from|const|let|return|class|function|new|if|throw)\b|\b\d+\b|\b[A-Za-z_$][\w$]*\b)/g);
  return <pre className="syntax-code"><code>{tokens.map((token, index) => <span key={index} className={/^['"]/.test(token) ? 'syntax-string' : /^(export|import|from|const|let|return|class|function|new|if|throw)$/.test(token) ? 'syntax-keyword' : /^\d/.test(token) ? 'syntax-number' : /^[A-Za-z_$]/.test(token) ? 'syntax-name' : undefined}>{token}</span>)}</code></pre>;
}
export function CopyCode({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return <button className="icon-control" aria-label="Copy code" onClick={async () => { try { await navigator.clipboard.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 1500); } catch { setCopied(false); } }}>{copied ? <Check size={13}/> : <Copy size={13}/>}</button>;
}
