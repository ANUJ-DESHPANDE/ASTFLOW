import { lazy, Suspense, useEffect, useRef, useState } from 'react';
import { Activity, ArrowDownUp, ArrowRight, BookOpen, Box, Braces, Check, ChevronDown, ChevronRight, CircleDot, Clock3, Command, Database, FileCode2, Folder, FolderGit2, GitBranch, GitCompareArrows, Info, Layers3, LoaderCircle, Plus, RefreshCw, Search, Settings2, ShieldCheck, Sparkles, Terminal, X } from 'lucide-react';
import { request } from './api/client';
import { ResultCard } from './components/ResultCard';
import type { Comparison, GraphData, GraphEdge, GraphNode, IndexStatus, Repository, Result, SearchResponse, Source, Version } from './types';

const EXAMPLES = ['Where is Bluetooth settings handled?', 'How does VoiceHandler reach BluetoothAgent?', 'Where is session restoration handled?', 'Where is authentication validated before a session is created?'];
const SourceViewer = lazy(() => import('./components/SourceViewer').then(module => ({ default: module.SourceViewer })));
const TraceGraph = lazy(() => import('./components/TraceGraph').then(module => ({ default: module.TraceGraph })));
type Mode = 'search' | 'trace' | 'changes';

function App() {
  const [repo, setRepo] = useState<Repository | null>(null);
  const [versions, setVersions] = useState<Version[]>([]);
  const [version, setVersion] = useState('working-tree');
  const [query, setQuery] = useState(EXAMPLES[0]);
  const [response, setResponse] = useState<SearchResponse | null>(null);
  const [selected, setSelected] = useState<Result | null>(null);
  const [source, setSource] = useState<Source | null>(null);
  const [selectedEdge, setSelectedEdge] = useState<GraphEdge | null>(null);
  const [mode, setMode] = useState<Mode>('search');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [initializing, setInitializing] = useState(true);
  const [status, setStatus] = useState<IndexStatus | null>(null);
  const [showRepo, setShowRepo] = useState(false);
  const [repoPath, setRepoPath] = useState('');
  const [draftPath, setDraftPath] = useState('');
  const [draftVersion, setDraftVersion] = useState('working-tree');
  const [agentic, setAgentic] = useState(true);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [graph, setGraph] = useState<GraphData | null>(null);
  const [traceFrom, setTraceFrom] = useState('VoiceHandler');
  const [traceTo, setTraceTo] = useState('BluetoothAgent');
  const [versionA, setVersionA] = useState('v1');
  const [versionB, setVersionB] = useState('v2');
  const [comparison, setComparison] = useState<Comparison | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const searchNumber = useRef(0);
  const sourceNumber = useRef(0);
  const indexing = status?.state === 'indexing';
  const manifest = repo?.indexes.find(i => i.version === version);
  const ready = Boolean(manifest);

  async function refresh() {
    const [repository, versionList] = await Promise.all([request<Repository>(`/repository?version=${encodeURIComponent(version)}`), request<{ versions: Version[] }>('/versions')]);
    setRepo(repository); setVersions(versionList.versions);
    const indexed = versionList.versions.filter(v => v.indexed).map(v => v.name);
    setVersionA(previous => indexed.includes(previous) ? previous : indexed[0] ?? '');
    setVersionB(previous => indexed.includes(previous) ? previous : indexed[1] ?? indexed[0] ?? '');
    setRepoPath(repository.path ?? repository.demo_path);
    return repository;
  }
  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        const repository = await refresh();
        if (mounted && repository.indexes.length) {
          const current = repository.indexes.find(i => i.version === 'working-tree')?.version ?? repository.indexes[0].version;
          setVersion(current); await search(EXAMPLES[0], current);
        }
      } catch (e) { if (mounted) setError((e as Error).message); }
      finally { if (mounted) setInitializing(false); }
    })();
    return () => { mounted = false; };
  }, []);
  useEffect(() => {
    if (showRepo) { setDraftPath(repo?.path ?? repo?.demo_path ?? ''); setDraftVersion(version); }
  }, [showRepo]);
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); input.current?.focus(); input.current?.select(); }
      if (event.key === 'Escape') { setSource(null); setShowRepo(false); }
    };
    window.addEventListener('keydown', handler); return () => window.removeEventListener('keydown', handler);
  }, []);
  useEffect(() => {
    if (!indexing) return;
    const poll = setInterval(async () => {
      try {
        const next = await request<IndexStatus>('/index/status'); setStatus(next);
        if (next.state === 'ready') { await refresh(); await search(query, version); }
        if (next.state === 'error') setError(next.stage);
      } catch (e) { setStatus({ state: 'error', stage: 'Connection lost', progress: 0 }); setError((e as Error).message); }
    }, 1000);
    return () => clearInterval(poll);
  }, [indexing, version]);

  async function search(text = query, targetVersion = version) {
    if (!text.trim()) return;
    const number = ++searchNumber.current;
    setBusy(true); setError(''); setSource(null); setSelectedEdge(null);
    try {
      const data = await request<SearchResponse>('/search', { query: text, version: targetVersion, top_k: 10, agentic });
      if (number !== searchNumber.current) return;
      setResponse(data); setSelected(data.results[0] ?? null); setGraph(data.graph);
    } catch (e) { if (number === searchNumber.current) setError((e as Error).message); }
    finally { if (number === searchNumber.current) setBusy(false); }
  }
  async function indexRepository(path = repoPath, targetVersion = version) {
    ++searchNumber.current; ++sourceNumber.current; setBusy(false);
    setError(''); setShowRepo(false); setResponse(null); setComparison(null); setSource(null);
    try {
      await request('/index', { repo_path: path, version: targetVersion, background: true });
      setVersion(targetVersion);
      setStatus({ state: 'indexing', stage: 'Reading source snapshot', progress: 0 });
    } catch (e) { setError((e as Error).message); }
  }
  async function openSource(path: string, start = 1, end?: number, snapshot = response?.version_key ?? manifest?.version_key ?? version) {
    const number = ++sourceNumber.current;
    try {
      const params = new URLSearchParams({ path, version: snapshot, start_line: String(start) });
      if (end) params.set('end_line', String(end));
      const data = await request<Source>(`/source?${params}`);
      if (number === sourceNumber.current) setSource(data);
    } catch (e) { setError((e as Error).message); }
  }
  function openResult(result: Result, snapshot?: string) {
    setSelected(result); setSelectedEdge(null); void openSource(result.file_path, result.start_line, result.end_line, snapshot);
  }
  function openEdge(edge: GraphEdge, snapshot?: string) {
    setSelectedEdge(edge); void openSource(edge.call_file, edge.call_line, edge.call_end_line, snapshot ?? graph?.version_key);
  }
  function openNode(node: GraphNode, snapshot?: string) { void openSource(node.file, node.start_line, node.end_line, snapshot ?? graph?.version_key); }
  async function runTrace() {
    setBusy(true); setError(''); setSource(null);
    try { setGraph(await request<GraphData>('/trace', { source_symbol_id: traceFrom, target_symbol_id: traceTo, version })); }
    catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  async function compare() {
    setBusy(true); setError(''); setSource(null);
    try { setComparison(await request<Comparison>('/compare', { query, version_a: versionA, version_b: versionB })); }
    catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  function changeVersion(next: string) {
    ++searchNumber.current; ++sourceNumber.current;
    setVersion(next); setSource(null); setResponse(null); setGraph(null); setSelected(null); setSelectedEdge(null); setBusy(false);
    void request<Repository>(`/repository?version=${encodeURIComponent(next)}`).then(setRepo).catch(e => setError(e.message));
    if (repo?.indexes.some(i => i.version === next)) void search(query, next);
  }
  function chooseExample(text: string) { setQuery(text); setMode('search'); if (ready) void search(text); }
  const folders = [...new Set((repo?.files ?? []).map(f => f.includes('/') ? f.split('/')[0] : '.'))];
  const indexedVersions = versions.filter(v => v.indexed);

  return <div className="app-shell">
    <header className="app-header">
      <a className="brand" href="/" aria-label="ASTFLOW home"><span className="brand-mark"><Layers3 size={22} strokeWidth={2.1}/></span>ASTFLOW<span className="beta">BETA</span></a>
      <div className="header-breadcrumb"><FolderGit2 size={16}/><button onClick={() => setShowRepo(true)}>{repo?.name ?? 'Local workspace'}</button><span className="slash">/</span><span className="muted">Investigation</span></div>
      <div className="header-right"><span className="local-badge"><span className="status-dot"/> Local workspace</span><a href="/docs" className="icon-button" title="API documentation" target="_blank" rel="noreferrer"><BookOpen size={17}/></a></div>
    </header>
    <aside className="sidebar">
      <div className="workspace-label">WORKSPACE <button className="icon-button" aria-label="Configure repository" onClick={() => setShowRepo(true)}><Settings2 size={14}/></button></div>
      <button className="repo-selector" onClick={() => setShowRepo(true)}><span className="repo-icon"><FolderGit2 size={19}/></span><span><strong>{repo?.name ?? 'Connect repository'}</strong><small>JavaScript repository</small></span><ChevronDown size={15}/></button>
      <div className="version-control"><GitBranch size={14}/><select aria-label="Repository version" value={version} onChange={e => changeVersion(e.target.value)} disabled={indexing}>
        {versions.length ? versions.map(v => <option value={v.name} key={v.name}>{v.name.length > 20 ? v.name.slice(0, 7) : v.name}{v.indexed ? '' : ' · not indexed'}</option>) : <option value="working-tree">Working tree</option>}
      </select></div>
      <nav className="side-nav" aria-label="Investigation views">
        {([['search', Search, 'Search'], ['trace', GitBranch, 'Trace'], ['changes', GitCompareArrows, 'Changes']] as const).map(([key, Icon, label]) => <button key={key} className={mode === key ? 'active' : ''} onClick={() => { setMode(key); setSource(null); }}><Icon size={17}/>{label}{key === 'search' && <kbd>⌘ K</kbd>}{key === 'changes' && <span className="nav-new">NEW</span>}</button>)}
      </nav>
      <div className="explorer-header"><span>EXPLORER</span><span>{repo?.files.length ?? 0} files</span></div>
      <div className="file-tree">
        {folders.map(folder => <div key={folder}><button className="folder-row" onClick={() => setCollapsed(previous => { const next = new Set(previous); next.has(folder) ? next.delete(folder) : next.add(folder); return next; })}>
          {collapsed.has(folder) ? <ChevronRight size={13}/> : <ChevronDown size={13}/>}<Folder size={15}/><span>{folder === '.' ? 'root' : folder}</span></button>
          {!collapsed.has(folder) && repo?.files.filter(f => folder === '.' ? !f.includes('/') : f.startsWith(folder + '/')).map(file => <button key={file} className={`file-row ${source?.path === file ? 'active' : ''}`} title={file} onClick={() => openSource(file, 1, undefined, manifest?.version_key)}><span className="js-icon">JS</span><span>{file.split('/').slice(folder === '.' ? 0 : 1).join('/')}</span></button>)}
        </div>)}
        {!folders.length && <p className="tree-empty">Index a repository to explore its source.</p>}
      </div>
      <div className="sidebar-bottom"><div className="index-state"><span className={`status-dot ${!ready ? 'dim' : ''}`}/><strong>{indexing ? 'Indexing source…' : ready ? 'Index ready' : 'No index yet'}</strong><button className="icon-button" aria-label="Reindex repository" disabled={indexing || !repoPath} onClick={() => indexRepository()}><RefreshCw size={14} className={indexing ? 'spin' : ''}/></button></div>
        <div className="index-stats">{manifest ? `${manifest.chunk_count} snippets · ${manifest.edge_count} relationships` : 'Source-backed results start here'}</div>
        <div className="local-note"><ShieldCheck size={13}/> Your code stays on this machine</div></div>
    </aside>

    <main className="main-workspace">
      <section className="search-area">
        <div className="page-eyebrow"><span className="tiny-line"/> REPOSITORY INTELLIGENCE</div>
        <div className="page-heading"><h1>{mode === 'changes' ? 'See what changed.' : mode === 'trace' ? 'Trace the path.' : 'Find the code.'}</h1><span>Every answer starts with evidence.</span></div>
        <form className={`search-box ${busy ? 'searching' : ''}`} onSubmit={e => { e.preventDefault(); mode === 'changes' ? void compare() : void search(); }}>
          <Search size={21}/><input ref={input} aria-label="Search repository" value={query} onChange={e => setQuery(e.target.value)} placeholder="Ask where something is implemented, used, or connected..."/>
          <kbd className="search-shortcut">Ctrl K</kbd><button className="primary-button" disabled={busy || indexing || !ready || !query.trim()} type="submit">{busy ? <LoaderCircle className="spin" size={16}/> : <ArrowRight size={16}/>}<span>Search</span></button>
        </form>
        <div className="search-options"><span><span className="status-dot"/>{manifest?.semantic.available ? 'Semantic + source search' : 'Source search'}<span className="option-divider">/</span>{version.length > 20 ? version.slice(0, 7) : version}</span>
          <label className="agent-toggle"><input type="checkbox" checked={agentic} onChange={e => setAgentic(e.target.checked)}/><span className="toggle-track"/><Sparkles size={13}/> Investigation mode</label></div>
        <nav className="mobile-nav" aria-label="Mobile investigation views">{(['search', 'trace', 'changes'] as const).map(view => <button key={view} className={mode === view ? 'active' : ''} onClick={() => { setMode(view); setSource(null); }}>{view}</button>)}</nav>
      </section>
      {error && <div role="alert" className="error-banner"><Info size={16}/><span>{error}</span><button className="icon-button" onClick={() => setError('')} aria-label="Dismiss error"><X size={15}/></button></div>}
      {indexing && <div className="index-progress"><div><LoaderCircle size={16} className="spin"/>{status.stage}<span>{status.progress}%</span></div><progress max="100" value={status.progress}/></div>}
      <div className="content-area"><Suspense fallback={<div className="empty-state"><LoaderCircle className="spin"/><p>Opening source tools…</p></div>}>
        {source ? <SourceViewer source={source} onClose={() => setSource(null)}/> : initializing ? <div className="empty-state"><LoaderCircle className="spin"/><p>Opening your workspace…</p></div> : !ready ? <div className="welcome-state">
          <div className="welcome-symbol"><Braces size={36}/></div><span className="page-eyebrow">YOUR NEXT INVESTIGATION</span><h2>Know where to look.</h2><p>Find relevant code, follow supported call paths, and see how answers change across versions.</p>
          <button className="primary-button" disabled={indexing} onClick={() => repo?.path ? indexRepository() : indexRepository(repo?.demo_path)}><Database size={16}/>{repo?.path ? `Index ${version}` : 'Explore the demo repository'}</button>
          <button className="text-button" onClick={() => setShowRepo(true)}>Open another repository <ArrowRight size={14}/></button>
          <div className="welcome-facts"><span><ShieldCheck size={16}/> Exact source evidence</span><span><GitBranch size={16}/> Verified relationships</span><span><GitCompareArrows size={16}/> Version aware</span></div>
        </div> : mode === 'search' ? <>
          <div className="results-toolbar"><div className="tab-label"><Search size={16}/> Search results <span className="count-badge">{response?.results.length ?? 0}</span></div><span className="results-meta">{response ? <><Clock3 size={12}/>{response.latency_ms.toFixed(0)} ms<span>·</span>Ranked by relevance</> : 'Ready to investigate'}</span></div>
          <div className="results-list">{response?.results.map(result => <ResultCard key={result.chunk_id} result={result} selected={selected?.chunk_id === result.chunk_id} onOpen={() => openResult(result)}/>)}
            {response && response.results.length === 0 && <div className="empty-state"><Search size={28}/><h3>No matching snippets</h3><p>Try a symbol name, behavior, or a different indexed version.</p></div>}
            {!response && <div className="empty-state"><Search size={28}/><h3>Start with a question</h3><p>Search your repository using natural language or a symbol name.</p></div>}
            {!!response?.results.length && <div className="results-end"><Check size={13}/> Retrieved from actual source in this snapshot</div>}
          </div>
        </> : mode === 'trace' ? <div className="trace-view">
          <div className="results-toolbar"><div className="tab-label"><GitBranch size={16}/> Structural trace</div><span className="results-meta">Source-backed relationships</span></div>
          <form className="trace-form" onSubmit={e => { e.preventDefault(); void runTrace(); }}><input aria-label="Trace source symbol" value={traceFrom} onChange={e => setTraceFrom(e.target.value)} placeholder="Source symbol"/><ArrowRight size={15}/><input aria-label="Trace target symbol" value={traceTo} onChange={e => setTraceTo(e.target.value)} placeholder="Target symbol"/><button className="secondary-button" disabled={busy}>Trace path</button></form>
          {graph?.message && <div className="graph-message">{graph.message}</div>}
          <TraceGraph graph={graph ?? { nodes: [], edges: [], paths: [] }} onNode={openNode} onEdge={openEdge}/>
          {!!graph?.edges.length && <details className="edge-list"><summary>Call-site evidence · {graph.edges.length} relationships</summary>{graph.edges.map((edge, i) => <button key={i} onClick={() => openEdge(edge)}><GitBranch size={13}/><code>{edge.source_expression}</code><span>{edge.call_file}:{edge.call_line}</span><ArrowRight size={13}/></button>)}</details>}
          <div className="supporting-title">SUPPORTING SEARCH RESULTS</div>{response?.results.slice(0, 3).map(result => <ResultCard key={result.chunk_id} result={result} compact onOpen={() => openResult(result)}/>)}
        </div> : <div className="changes-view">
          <div className="results-toolbar"><div className="tab-label"><GitCompareArrows size={16}/> Change radar</div><span className="results-meta">One question. Two snapshots.</span></div>
          <form className="compare-form" onSubmit={e => { e.preventDefault(); void compare(); }}><GitBranch size={16}/><select aria-label="Version A" value={versionA} onChange={e => setVersionA(e.target.value)}>{indexedVersions.map(v => <option key={v.name} value={v.name}>{v.label}</option>)}</select><ArrowRight size={16}/><select aria-label="Version B" value={versionB} onChange={e => setVersionB(e.target.value)}>{indexedVersions.map(v => <option key={v.name} value={v.name}>{v.label}</option>)}</select><button className="secondary-button" disabled={busy || indexedVersions.length < 2}>Compare</button></form>
          {indexedVersions.length < 2 && <div className="graph-message">Index two Git versions using the sidebar version selector to compare their source.</div>}
          {comparison ? <><div className="change-stats"><span><strong className="accent">+{comparison.relevant_changes.added_symbols.length}</strong> relevant symbols added</span><span><strong className="amber">~{comparison.relevant_changes.modified_symbols.length}</strong> modified</span><span><strong>+{comparison.changes.added_edges.length}</strong> call relationships</span></div>
            <div className="comparison-columns">{(['a', 'b'] as const).map(side => <section key={side}><h3><GitBranch size={14}/>{side === 'a' ? comparison.version_a : comparison.version_b}<span>{side === 'a' ? 'BEFORE' : 'AFTER'}</span></h3>{(side === 'a' ? comparison.results_a : comparison.results_b).slice(0, 5).map(result => <ResultCard key={result.chunk_id} result={result} compact onOpen={() => openResult(result, side === 'a' ? comparison.version_key_a : comparison.version_key_b)}/>)}</section>)}</div>
            <details className="change-details" open><summary>Retrieval rank changes</summary>{comparison.rank_changes.filter(r => r.rank_a !== r.rank_b).slice(0, 10).map(row => <div key={row.symbol_id}><code>{row.symbol_id.split('::')[1]}</code><span>{row.rank_a ?? '—'} <ArrowRight size={12}/> {row.rank_b ?? '—'}</span></div>)}</details>
            <details className="change-details"><summary>Structural changes · +{comparison.changes.added_edges.length} / −{comparison.changes.removed_edges.length}</summary>{comparison.changes.added_edges.map((edge, i) => <button className="change-edge" key={`added-${i}`} onClick={() => openEdge(edge, comparison.version_key_b)}><Plus size={13}/><code>{edge.source_expression}</code><span>{edge.call_file}:{edge.call_line}</span></button>)}
              {comparison.changes.removed_edges.map((edge, i) => <button className="change-edge removed" key={`removed-${i}`} onClick={() => openEdge(edge, comparison.version_key_a)}><span aria-label="Removed">−</span><code>{edge.source_expression}</code><span>{edge.call_file}:{edge.call_line}</span></button>)}
              <h4 className="supporting-title">BEFORE · {comparison.version_a}</h4><TraceGraph graph={comparison.graph_a} onNode={n => openNode(n, comparison.version_key_a)} onEdge={e => openEdge(e, comparison.version_key_a)}/>
              <h4 className="supporting-title">AFTER · {comparison.version_b}</h4><TraceGraph graph={comparison.graph_b} onNode={n => openNode(n, comparison.version_key_b)} onEdge={e => openEdge(e, comparison.version_key_b)}/></details>
          </> : <div className="empty-state"><GitCompareArrows size={32}/><h3>Follow the refactor.</h3><p>Compare the same query across two indexed versions to see changes in ranked results and call relationships.</p></div>}
        </div>}
      </Suspense></div>
    </main>

    <aside className="investigation-panel">
      <div className="panel-heading"><Activity size={16}/><strong>Investigation</strong><span className="count-badge">{response?.agent_trace.filter(s => s.step === 'SEARCH').length ?? 0} passes</span></div>
      <div className="panel-scroll"><section className="panel-section"><div className="section-label">SEARCH ACTIVITY <span className="live-pill">{busy ? 'RUNNING' : response ? 'COMPLETE' : 'READY'}</span></div>
        {response ? <ol className="activity-timeline">{response.agent_trace.map((step, i) => <li key={i}><span className={`timeline-dot ${step.step === 'REFINE' ? 'refine' : ''}`}>{step.step === 'REFINE' ? <Sparkles size={11}/> : <Check size={11}/>}</span><div><strong>{({ PLAN: 'Search plan', SEARCH: 'Retrieve evidence', OBSERVE: 'Inspect results', REFINE: 'Refine investigation', RERANK: 'Rank candidates', STOP: 'Investigation complete' } as Record<string, string>)[step.step]}</strong><p>{step.details}</p></div></li>)}</ol> : <p className="muted panel-description">Your search activity will appear here, with each evidence-gathering step made visible.</p>}
      </section>
      <section className="panel-section"><div className="section-label">{selectedEdge ? 'CALL-SITE EVIDENCE' : 'RESULT EVIDENCE'}<ShieldCheck size={14}/></div>
        {selectedEdge ? <div className="edge-evidence"><span className="chip structural">{selectedEdge.evidence_type.replaceAll('_', ' ')}</span><code>{selectedEdge.source_expression}</code><p className="mono">{selectedEdge.call_file}:{selectedEdge.call_line}</p><div className="evidence-fact"><span>Resolution</span><strong>{selectedEdge.resolution_method.replaceAll('_', ' ')}</strong></div>{selectedEdge.evidence_sources.map(s => <div className="evidence-fact" key={s}><span>{s.replaceAll('_', ' ')}</span><Check size={13}/></div>)}</div> : selected ? <><div className="selected-symbol"><Braces size={15}/><strong className="mono">{selected.qualified_name}</strong></div>
          <div className="evidence-fact"><span>Text relevance</span><strong>{selected.evidence.lexical_rank ? `Rank #${selected.evidence.lexical_rank}` : 'No match'}</strong></div>
          <div className="evidence-fact"><span>Semantic relevance</span><strong>{selected.evidence.semantic_rank ? `Rank #${selected.evidence.semantic_rank}` : 'Unavailable / no match'}</strong></div>
          <div className="evidence-fact"><span>Exact symbol</span>{selected.evidence.exact_symbol_match ? <Check className="accent" size={14}/> : <span>—</span>}</div>
          <div className="evidence-fact"><span>Structural proximity</span><strong>{selected.evidence.structural_distance ? `${selected.evidence.structural_distance} hop(s)` : '—'}</strong></div>
          <div className="evidence-note"><Info size={14}/><p>Search relevance is an inference. Call relationships are verified separately against source.</p></div>
          <details className="score-details"><summary>Ranking diagnostics <ChevronDown size={12}/></summary>{Object.entries(selected.evidence.contributions).map(([name, score]) => <div className="evidence-fact" key={name}><span>{name.replaceAll('_', ' ')}</span><code>{score.toFixed(5)}</code></div>)}</details>
        </> : <p className="muted panel-description">Select a result or graph edge to inspect its supporting evidence.</p>}
      </section>
      {!!response?.sequences.length && <section className="panel-section"><div className="section-label">SEQUENCE EVIDENCE</div>{response.sequences.map((s, i) => <div className="sequence-evidence" key={i}><code>{s.before.split('::')[1]}</code><span>LEXICALLY BEFORE</span><code>{s.after.split('::')[1]}</code><p>{s.explanation}</p></div>)}</section>}
      <section className="panel-section examples"><div className="section-label">KEEP EXPLORING <Sparkles size={13}/></div>{EXAMPLES.slice(1).map(q => <button key={q} onClick={() => chooseExample(q)}>{q}<ArrowRight size={13}/></button>)}</section>
      {manifest && <details className="panel-section index-diagnostics"><summary>Index diagnostics</summary><p>{manifest.semantic.message}</p><p>Language service: {manifest.enrichment.status} · {manifest.enrichment.edges_confirmed} confirmed calls</p><p>Built in {manifest.index_latency_ms.toFixed(0)} ms · {manifest.file_count} source files</p>{manifest.warnings.map(w => <p key={w}>{w}</p>)}</details>}
      </div><div className="panel-bottom"><ShieldCheck size={13}/> Evidence, not guesswork.</div>
    </aside>
    <footer className="status-bar"><span><span className="status-dot"/> ASTFLOW engine</span><span><Braces size={12}/> JavaScript</span><span className="footer-tagline">Find the code. Trace the path. See what changed.</span><span>CPU · Local</span></footer>
    {showRepo && <div className="modal-backdrop" onClick={() => setShowRepo(false)}><section className="repo-dialog" role="dialog" aria-modal="true" aria-label="Open repository" onClick={e => e.stopPropagation()}><div className="dialog-heading"><FolderGit2 size={22}/><h2>Open a repository</h2><button className="icon-button" aria-label="Close dialog" onClick={() => setShowRepo(false)}><X size={18}/></button></div><p>Enter the local path to a JavaScript repository. ASTFLOW reads source files without executing repository code.</p><form onSubmit={e => { e.preventDefault(); void indexRepository(draftPath, draftVersion); }}><label htmlFor="repo-path">Repository path</label><input id="repo-path" value={draftPath} onChange={e => setDraftPath(e.target.value)} placeholder="C:\projects\my-repository" autoFocus/><label htmlFor="repo-version">Git revision or working tree</label><input id="repo-version" value={draftVersion} onChange={e => setDraftVersion(e.target.value)} placeholder="working-tree, HEAD, tag, or commit"/><button className="primary-button" disabled={!draftPath.trim() || indexing}><Database size={16}/>Index repository</button></form><button className="text-button" onClick={() => { setDraftPath(repo?.demo_path ?? ''); setDraftVersion('working-tree'); }}>Use the included demo <ArrowRight size={13}/></button></section></div>}
  </div>;
}

export default App;
