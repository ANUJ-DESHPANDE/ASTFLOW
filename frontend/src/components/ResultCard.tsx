import { ArrowUpRight, Braces, GitBranch, ScanText, ShieldCheck, Sparkles } from 'lucide-react';
import type { Result } from '../types';

export function ResultCard({ result, selected, onOpen, compact = false }: {
  result: Result; selected?: boolean; onOpen: () => void; compact?: boolean;
}) {
  const e = result.evidence;
  return <button className={`result-card ${selected ? 'selected' : ''} ${compact ? 'result-compact' : ''}`} onClick={onOpen} aria-label={`Open ${result.qualified_name}`}>
    <div className="result-heading"><span className="rank">{String(result.rank).padStart(2, '0')}</span>
      <span className="symbol-icon"><Braces size={16}/></span><strong className="mono">{result.qualified_name}</strong>
      <span className="kind-label">{result.kind.replace('_', ' ')}</span><ArrowUpRight size={16} className="open-arrow"/></div>
    <div className="result-path mono">{result.file_path}<span>:</span><span className="line-number">{result.start_line}–{result.end_line}</span></div>
    {!compact && <div className="code-preview">{result.snippet.split('\n').slice(0, 4).map((line, i) => <div className="code-line" key={i}>
      <span className="code-line-number">{result.start_line + i}</span><code>{line}</code></div>)}</div>}
    <div className="result-footer"><div className="evidence-chips">
      {e.exact_symbol_match && <span className="chip exact"><ScanText size={11}/> Exact symbol</span>}
      {e.semantic_rank && <span className="chip semantic"><Sparkles size={11}/> Semantic match</span>}
      {e.lexical_rank && <span className="chip">Text match</span>}
      {e.structural_distance && <span className="chip structural"><GitBranch size={11}/> Connected code</span>}
      {e.test_reference && <span className="chip"><ShieldCheck size={11}/> Test reference</span>}
    </div><span className="result-score mono" title="Fused ranking score, not a probability">{result.score.toFixed(4)}</span></div>
  </button>;
}
