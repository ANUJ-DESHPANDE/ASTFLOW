import { lazy, Suspense, useEffect, useRef, useState } from 'react';
import { Check, ChevronDown, FileCode2, Folder, GitBranch, GitCompareArrows, Plus, RefreshCw, Search, Settings2, Sparkles, X } from 'lucide-react';
import { request } from './api/client';
import { FileTree } from './components/FileTree';
import { FlowMark, CodeSnippet, CopyCode } from './components/StudioParts';
import { SequenceEvidence } from './components/SequenceEvidence';
import { ArrowUp, ArrowUpRight, Copy, Maximize2, MessageSquare, PanelLeft } from 'lucide-react';

import type { Comparison, GraphData, GraphEdge, GraphNode, IndexStatus, Repository, Result, SearchResponse, Source, Version } from './types';

const SourceDiff = lazy(() => import('./components/SourceViewer').then(module => ({ default: module.SourceDiff })));
const SourceViewer = lazy(() => import('./components/SourceViewer').then(module => ({ default: module.SourceViewer })));
const TraceGraph = lazy(() => import('./components/TraceGraph').then(module => ({ default: module.TraceGraph })));
type Mode = 'map' | 'search' | 'trace' | 'changes';

function App() {
  const [repo, setRepo] = useState<Repository | null>(null);
  const [versions, setVersions] = useState<Version[]>([]);
  const [version, setVersion] = useState('working-tree');
  const [query, setQuery] = useState('');
  const [response, setResponse] = useState<SearchResponse | null>(null);
  const [selected, setSelected] = useState<Result | null>(null);
  const [source, setSource] = useState<Source | null>(null);
  const [selectedEdge, setSelectedEdge] = useState<GraphEdge | null>(null);
  const [mode, setMode] = useState<Mode>('search');
  const [overview, setOverview] = useState<GraphData | null>(null);
  const [mapFile, setMapFile] = useState('');
  const [mapSymbol, setMapSymbol] = useState('');
  const [edgeSnapshot, setEdgeSnapshot] = useState('');
  const [sourceChanged, setSourceChanged] = useState(false);
  const [assistantOpen, setAssistantOpen] = useState(() => window.innerWidth > 850);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [initializing, setInitializing] = useState(true);
  const [status, setStatus] = useState<IndexStatus | null>(null);
  const [showRepo, setShowRepo] = useState(false);
  const [repoPath, setRepoPath] = useState('');
  const [draftPath, setDraftPath] = useState('');
  const [draftVersion, setDraftVersion] = useState('working-tree');
  const [agentic, setAgentic] = useState(true);
  const [graph, setGraph] = useState<GraphData | null>(null);
  const [traceFrom, setTraceFrom] = useState('VoiceHandler');
  const [traceTo, setTraceTo] = useState('BluetoothAgent');
  const [versionA, setVersionA] = useState('v1');
  const [versionB, setVersionB] = useState('v2');
  const [comparison, setComparison] = useState<Comparison | null>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  const searchNumber = useRef(0);
  const sourceNumber = useRef(0);
  const actionNumber = useRef(0);
  const contextNumber = useRef(0);
  const indexing = status?.state === 'indexing';
  const manifest = repo?.indexes.find(i => i.version === version);
  const ready = Boolean(manifest);

  async function refresh() {
    const context = contextNumber.current;
    const [repository, versionList] = await Promise.all([request<Repository>(`/repository?version=${encodeURIComponent(version)}`), request<{ versions: Version[] }>('/versions')]);
    if (context !== contextNumber.current) return repository;
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
          setVersion(current);
          const active = current === 'working-tree' ? repository : await request<Repository>(`/repository?version=${encodeURIComponent(current)}`);
          if (!mounted) return;
          setRepo(active);
          if(active.files[0]) await openSource(active.files[0], 1, undefined, current);
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
      const dialog = document.querySelector<HTMLElement>('[role="dialog"]');
      if (dialog && event.key === 'Tab') {
        const controls = [...dialog.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), select:not(:disabled), a[href]')];
        const first = controls[0], last = controls[controls.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
      }
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); setAssistantOpen(true); setTimeout(() => { input.current?.focus(); input.current?.select(); }, 0); }
      if (event.key === 'Escape') {
        setShowRepo(false);
        // assistantOpen/explorerOpen are mobile drawer flags below these breakpoints
        // (see the >850px and >600px media queries); above them the companion panel
        // has no close affordance, so Escape must not hide it there.
        if (window.innerWidth <= 850) setAssistantOpen(false);
        if (window.innerWidth <= 600) setExplorerOpen(false);
      }
    };
    window.addEventListener('keydown', handler); return () => window.removeEventListener('keydown', handler);
  }, []);
  useEffect(() => {
    if (!indexing) return;
    const poll = setInterval(async () => {
      try {
        const next = await request<IndexStatus>('/index/status'); setStatus(next);
        if (next.state === 'ready') { const updated = await refresh(); if (query.trim()) await search(query, version); else if (updated.files[0]) await openSource(updated.files[0], 1, undefined, version); }
        if (next.state === 'error') setError(next.stage);
      } catch (e) { setStatus({ state: 'error', stage: 'Connection lost', progress: 0 }); setError((e as Error).message); }
    }, 1000);
    return () => clearInterval(poll);
  }, [indexing, version]);

  async function search(text = query, targetVersion = version) {
    if (!text.trim()) return;
    const number = ++searchNumber.current;
    ++actionNumber.current; ++sourceNumber.current;
    setBusy(true); setError(''); setSource(null); setSelectedEdge(null);
    try {
      const data = await request<SearchResponse>('/search', { query: text, version: targetVersion, top_k: 10, agentic });
      if (number !== searchNumber.current) return;
      setResponse(data); setSelected(data.results[0] ?? null); setGraph(data.graph);
      if (data.results[0]) { const first = data.results[0]; void openSource(first.file_path, first.start_line, first.end_line, data.version_key); }
    } catch (e) { if (number === searchNumber.current) setError((e as Error).message); }
    finally { if (number === searchNumber.current) setBusy(false); }
  }
  async function indexRepository(path = repoPath, targetVersion = version) {
    ++contextNumber.current; ++actionNumber.current; ++searchNumber.current; ++sourceNumber.current; setBusy(false); setGraph(null); setOverview(null);
    setMapFile(''); setMapSymbol(''); setComparisonSources({}); setTabs([]); setTurns([]); setDiff(null); setError(''); setShowRepo(false); setResponse(null); setComparison(null); setSource(null);
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
      if (number === sourceNumber.current) { setSource(data); setMode('search'); }
    } catch (e) { if (number === sourceNumber.current) setError((e as Error).message); }
  }
  function narrow() { return window.innerWidth <= 850; }
  function openResult(result: Result, snapshot?: string) {
    setSelected(result); setSelectedEdge(null); if (narrow()) setAssistantOpen(false); void openSource(result.file_path, result.start_line, result.end_line, snapshot);
  }
  /** A source link inside the companion; on narrow screens the drawer closes so the opened lines are visible. */
  function openFromCompanion(file: string, start: number, end: number | undefined, snapshot?: string) {
    if (narrow()) setAssistantOpen(false);
    void openSource(file, start, end, snapshot);
  }
  function openEdge(edge: GraphEdge, snapshot?: string) {
    setEdgeSnapshot(snapshot ?? graph?.version_key ?? manifest?.version_key ?? version); setSelectedEdge(edge); void openSource(edge.call_file, edge.call_line, edge.call_end_line, snapshot ?? graph?.version_key);
  }
  function openNode(node: GraphNode, snapshot?: string) { void openSource(node.file, node.start_line, node.end_line, snapshot ?? graph?.version_key); }
  function invalidateView() {
    ++actionNumber.current; ++searchNumber.current; ++sourceNumber.current;
    setBusy(false); setSource(null);
  }
  function chooseMode(next: Mode) { invalidateView(); setMode(next); }
  async function runTrace() {
    invalidateView(); const number = ++actionNumber.current;
    setBusy(true); setError('');
    try {
      const data = await request<GraphData>('/trace', { source_symbol_id: traceFrom, target_symbol_id: traceTo, version });
      if (number === actionNumber.current) setGraph(data);
    } catch (e) { if (number === actionNumber.current) setError((e as Error).message); }
    finally { if (number === actionNumber.current) setBusy(false); }
  }
  async function compare() {
    invalidateView(); const number = ++actionNumber.current;
    setResponse(null); setSelected(null); setSelectedEdge(null); setComparison(null); setDiff(null);
    if (!narrow()) setAssistantOpen(true);
    setBusy(true); setError('');
    try {
      const data = await request<Comparison>('/compare', { query: query.trim() || 'What changed in this repository?', version_a: versionA, version_b: versionB });
      if (number === actionNumber.current) setComparison(data);
    } catch (e) { if (number === actionNumber.current) setError((e as Error).message); }
    finally { if (number === actionNumber.current) setBusy(false); }
  }
  function changeVersion(next: string) {
    invalidateView(); const context = ++contextNumber.current;
    setMapFile(''); setMapSymbol(''); setSourceChanged(false);
    setTabs([]); setTurns([]); setDiff(null); setVersion(next); setResponse(null); setGraph(null); setOverview(null); setComparison(null); setSelected(null); setSelectedEdge(null);
    void request<Repository>(`/repository?version=${encodeURIComponent(next)}`).then(data => { if (context === contextNumber.current) setRepo(data); }).catch(e => { if (context === contextNumber.current) setError(e.message); });
    if (repo?.indexes.some(i => i.version === next)) void search(query, next);
  }
  useEffect(() => {
    let cancelled = false;
    if (manifest) void request<GraphData>(`/map?version=${manifest.version_key}&file=${encodeURIComponent(mapFile)}&symbol=${encodeURIComponent(mapSymbol)}&depth=3`).then(data => { if (!cancelled) setOverview(data); }).catch(e => { if (!cancelled) setError(e.message); });
    return () => { cancelled = true; };
  }, [manifest?.version_key, mapFile, mapSymbol]);
  useEffect(() => {
    if (!ready || version !== 'working-tree' || indexing) return;
    let cancelled = false, inFlight = false;
    const timer = setInterval(async () => {
      if (document.hidden || inFlight) return;
      inFlight = true;
      try {
        const data = await request<{ changed: boolean; version_key: string }>('/checkpoint');
        if (!cancelled && data.version_key === manifest?.version_key) setSourceChanged(data.changed);
      } catch { /* Passive checks never interrupt an investigation. */ }
      finally { inFlight = false; }
    }, 15000);
    return () => { cancelled = true; clearInterval(timer); };
  }, [ready, version, indexing, manifest?.version_key]);
  const indexedVersions = versions.filter(v => v.indexed);

  const [tabs, setTabs] = useState<Source[]>([]);
  const [filterOpen, setFilterOpen] = useState(false);
  const [filter, setFilter] = useState('');
  const [explorerOpen, setExplorerOpen] = useState(false);
  const [explorerHidden, setExplorerHidden] = useState(false);
  const [zoom, setZoom] = useState(100);
  const [turns, setTurns] = useState<{ search?: SearchResponse; comparison?: Comparison }[]>([]);
  const [comparisonSources, setComparisonSources] = useState<Record<string, {before: Source; after: Source}>>({});
  const [diff, setDiff] = useState<{ before: Source; after: Source } | null>(null);
  const conversation = useRef<HTMLDivElement>(null);
  const workspace = useRef<HTMLElement>(null);
  useEffect(() => {
    if (source) setTabs(old => old.some(t => t.path === source.path && t.version_key === source.version_key) ? old.map(t => t.path === source.path && t.version_key === source.version_key ? source : t) : [...old, source]);
  }, [source]);
  useEffect(() => { if (response) setTurns(old => [...old, { search: response }]); }, [response]);
  useEffect(() => { if (comparison) { setTurns(old => old.some(t => t.comparison === comparison) ? old : [...old, { comparison }]); const id = comparison.changes.modified_symbols[0]; if (id) void showDiff(comparison, id); } }, [comparison]);
  useEffect(() => { conversation.current?.scrollTo({ top: conversation.current.scrollHeight, behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth' }); }, [turns.length, busy]);
  async function showDiff(data: Comparison, id: string) {
    const number = ++sourceNumber.current, context = contextNumber.current;
    const file = id.split('::')[0];
    try {
      const [before, after] = await Promise.all([request<Source>(`/source?${new URLSearchParams({ path: file, version: data.version_key_a })}`), request<Source>(`/source?${new URLSearchParams({ path: file, version: data.version_key_b })}`)]);
      if (number === sourceNumber.current && context === contextNumber.current) { setDiff({ before, after }); setComparisonSources(old => ({...old, [data.version_key_a + ':' + data.version_key_b]: {before,after}})); setMode('changes'); }
    } catch (e) { if (number === sourceNumber.current) setError((e as Error).message); }
  }
  function switchView(next: Mode) {
    chooseMode(next);
    if (next === 'search') setSource(tabs.at(-1) ?? null);
    setExplorerOpen(false);
  }
  function closeTab(tab: Source) {
    ++sourceNumber.current;
    const next = tabs.filter(t => t !== tab); setTabs(next);
    if (source?.path === tab.path && source?.version_key === tab.version_key) setSource(next.at(-1) ?? null);
  }
  function ask(text = query) { if (!text.trim() || busy || !ready) return; setQuery(''); setAssistantOpen(true); void search(text); }
  async function explainCurrent() {
    const text = source
      ? `Explain what ${source.path.split('/').at(-1)?.replace(/\.[^.]+$/, '')} does, what its main functions are, and how it connects to the rest of the codebase`
      : 'Explain the main entry point and how the application is structured';
    if (busy || !ready) return;
    const number = ++searchNumber.current;
    ++actionNumber.current;
    // Deliberately do NOT increment sourceNumber — we keep the current file open in the viewer.
    setBusy(true); setError(''); setSelectedEdge(null); setAssistantOpen(true);
    try {
      const data = await request<SearchResponse>('/search', { query: text, version, top_k: 10, agentic });
      if (number !== searchNumber.current) return;
      setResponse(data); setSelected(data.results[0] ?? null); setGraph(data.graph);
      // No openSource call — the source viewer stays on the currently open file.
    } catch (e) { if (number === searchNumber.current) setError((e as Error).message); }
    finally { if (number === searchNumber.current) setBusy(false); }
  }
  function diffPair(data: Comparison) {
    const id = data.changes.modified_symbols.find(id => data.results_a.some(r => r.symbol_id === id) && data.results_b.some(r => r.symbol_id === id));
    const saved = comparisonSources[data.version_key_a + ':' + data.version_key_b];
    if (!id && saved) return [saved.before, saved.after].map(s => ({snippet: s.full_content, file_path: s.path, start_line: 1, end_line: s.total_lines}));
    return [data.results_a.find(r => r.symbol_id === id), data.results_b.find(r => r.symbol_id === id)];
  }

  return <div className={`studio ${assistantOpen ? 'show-chat' : ''} ${explorerOpen ? 'show-explorer' : ''} ${explorerHidden ? 'hide-explorer' : ''}`}>
    <header className="topbar">
      <h1 className="sr-only">ASTFLOW repository workspace</h1>
      <a className="wordmark" href="/" aria-label="ASTFLOW home"><FlowMark/><span>Astflow</span></a>
      <button className="project-picker" onClick={() => setShowRepo(true)}><span>{repo?.name ?? 'Open a repository'}</span><ChevronDown size={13}/></button>
      <nav className="view-switch" aria-label="Workspace views">{([['map','Map'],['changes','Compare'],['search','Code']] as const).map(([key,label]) => <button key={key} className={mode === key || key === 'map' && mode === 'trace' ? 'selected' : ''} onClick={() => switchView(key)}>{label}</button>)}</nav>
      <div className="topbar-actions"><button className="blue-button" aria-expanded={assistantOpen} onClick={() => setAssistantOpen(v => !v)}>Ask</button></div>
    </header>
    <aside className="tool-rail" aria-label="Workspace tools"><button className={mode === 'search' ? 'active' : ''} title="Explorer" aria-label="Explorer" onClick={() => window.innerWidth <= 600 ? setExplorerOpen(v => !v) : setExplorerHidden(v => !v)}><Folder size={21} fill="currentColor"/></button><button title="System map" aria-label="System map" className={mode === 'map' ? 'active' : ''} onClick={() => switchView('map')}><GitBranch size={21}/></button><button title="Compare versions" aria-label="Compare versions" className={mode === 'changes' ? 'active' : ''} onClick={() => switchView('changes')}><GitCompareArrows size={21}/></button><div className="rail-spacer"/><button aria-label="Repository settings" title="Repository settings" onClick={() => setShowRepo(true)}><Settings2 size={20}/></button></aside>
    <aside className="explorer"><div className="explorer-title"><strong>Explorer</strong><button className="icon-control" aria-label="Filter files" onClick={() => setFilterOpen(v => !v)}><Search size={16}/></button></div>{filterOpen && <input autoFocus className="file-filter" aria-label="Filter repository files" placeholder="Find a file…" value={filter} onChange={e => setFilter(e.target.value)}/>}
      <FileTree files={(repo?.files ?? []).filter(file => file.toLowerCase().includes(filter.toLowerCase()))} selected={source?.path} onOpen={file => { setExplorerOpen(false); void openSource(file, 1, undefined, manifest?.version_key); }}/>
      <div className="explorer-foot"><PanelLeft size={16}/><select aria-label="Repository version" value={version} disabled={indexing} onChange={e => changeVersion(e.target.value)}>{versions.length ? versions.map(v => <option key={v.name} value={v.name}>{v.label}{v.indexed ? '' : ' · not indexed'}</option>) : <option>working-tree</option>}</select><button className="icon-control" aria-label="Reindex repository" title="Reindex repository" disabled={busy || indexing || !repoPath} onClick={() => void indexRepository()}><RefreshCw size={13}/></button></div>
    </aside>
    <main className="editor-workspace" ref={workspace}>
      <div className="editor-tabs"><div className="open-tabs" role="group" aria-label="Open source files">{mode === 'search' ? tabs.map(tab => <div key={`${tab.version_key}:${tab.path}`} className={`file-tab ${source?.path === tab.path && source?.version_key === tab.version_key ? 'selected' : ''}`}><button aria-current={source?.path === tab.path && source?.version_key === tab.version_key ? 'true' : undefined} title={`${tab.path} · ${tab.version_key.slice(0,8)}`} onClick={() => { ++sourceNumber.current; setSource(tab); }}><span className="file-badge">JS</span>{tab.path.split('/').at(-1)}</button><button className="close-tab" aria-label={`Close ${tab.path}`} onClick={() => closeTab(tab)}><X size={12}/></button></div>) : <div className="workspace-label">{mode === 'changes' ? <GitCompareArrows size={15}/> : <GitBranch size={15}/>} {mode === 'changes' ? 'Compare snapshots' : 'Repository map'}</div>}{mode === 'search' && <button className="icon-control add-tab" aria-label="Find another file" onClick={() => { setFilterOpen(true); setExplorerHidden(false); setExplorerOpen(true); }}><Plus size={15}/></button>}</div>
        <div className="editor-tools"><select aria-label="Editor zoom" value={zoom} onChange={e => setZoom(Number(e.target.value))}>{[80,88,100,110,125,150].map(n => <option key={n} value={n}>{n}%</option>)}</select><span/><button className="icon-control" aria-label="Copy selected source" disabled={!source} onClick={() => source && void navigator.clipboard.writeText(source.content).catch(() => setError('Clipboard unavailable.'))}><Copy size={14}/></button><button className="icon-control" aria-label="Expand workspace" onClick={() => document.fullscreenElement ? void document.exitFullscreen() : void workspace.current?.requestFullscreen().catch(() => setError('Fullscreen unavailable.'))}><Maximize2 size={14}/></button></div>
      </div>
      {sourceChanged && <div className="quiet-notice">New source changes available.<button disabled={busy || indexing} onClick={() => { setSourceChanged(false); void indexRepository(); }}>Update snapshot</button></div>}
      {error && <div className="error-notice" role="alert"><span>{error}</span><button aria-label="Dismiss error" onClick={() => setError('')}><X size={14}/></button></div>}
      <Suspense fallback={<div className="workspace-empty"><FlowMark loading/><p>Opening source tools…</p></div>}>
      {initializing || indexing ? <div className="workspace-empty"><FlowMark loading/><h2>{indexing ? 'Reading your repository…' : 'Opening your workspace…'}</h2><p>{status?.stage}</p>{indexing && <progress max="100" value={status?.progress}/>}</div> : !ready ? <div className="workspace-empty"><FlowMark/><h2>Your code. A clearer picture.</h2><p>{repo?.path ? `Index ${version} to explore this snapshot.` : 'Open a JavaScript repository to explore its source, connections and changes.'}</p><button className="glass-button" onClick={() => void indexRepository(repo?.path ?? repo?.demo_path)}>{repo?.path ? 'Index snapshot' : 'Explore demo'}<ArrowUpRight size={14}/></button></div> : mode === 'search' ? source ? <SourceViewer source={source} zoom={zoom}/> : <div className="workspace-empty"><FileCode2 size={28}/><p>Select a file from the explorer.</p></div> : mode === 'changes' ? <>
        <form className="compare-controls" onSubmit={e => { e.preventDefault(); void compare(); }}><select aria-label="Version A" value={versionA} onChange={e => { invalidateView(); setComparison(null); setDiff(null); setVersionA(e.target.value); }}>{indexedVersions.map(v => <option key={v.name} value={v.name}>{v.label}</option>)}</select><span>→</span><select aria-label="Version B" value={versionB} onChange={e => { invalidateView(); setComparison(null); setDiff(null); setVersionB(e.target.value); }}>{indexedVersions.map(v => <option key={v.name} value={v.name}>{v.label}</option>)}</select><button className="glass-button" disabled={busy || indexedVersions.length < 2}>Compare</button></form>
        {comparison && <div className="change-selector"><select aria-label="Changed symbol" onChange={e => void showDiff(comparison, e.target.value)}>{comparison.changes.modified_symbols.map(id => <option key={id}>{id}</option>)}</select><span>+{comparison.changes.added_symbols.length} / −{comparison.changes.removed_symbols.length} symbols</span></div>}
        {diff ? <SourceDiff before={diff.before} after={diff.after} zoom={zoom}/> : <div className="workspace-empty"><GitCompareArrows size={28}/><h2>See the change in context.</h2><p>{indexedVersions.length < 2 ? 'Index two Git revisions to compare their source.' : comparison ? 'No shared modified source. Inspect additions and removals in the companion.' : 'Choose two snapshots to inspect the source and supported connections.'}</p></div>}
      </> : <><div className="map-controls"><select aria-label="Map file focus" value={mapFile} onChange={e => { setMapFile(e.target.value); setMapSymbol(''); setMode('map'); }}><option value="">All source files</option>{repo?.files.map(file => <option key={file}>{file}</option>)}</select><button className="glass-button" onClick={() => switchView(mode === 'trace' ? 'map' : 'trace')}><GitBranch size={13}/>Trace a path</button></div>
        {mode === 'trace' && <form className="trace-controls" onSubmit={e => { e.preventDefault(); void runTrace(); }}><input aria-label="Trace source symbol" value={traceFrom} onChange={e => setTraceFrom(e.target.value)} placeholder="From symbol"/><span>→</span><input aria-label="Trace target symbol" value={traceTo} onChange={e => setTraceTo(e.target.value)} placeholder="To symbol"/><button className="glass-button" disabled={busy || !traceFrom.trim() || !traceTo.trim()}>Trace</button></form>}
        {mapSymbol && mode === 'map' && <button className="source-link map-breadcrumb" onClick={() => setMapSymbol('')}>Back to {mapFile || 'repository'} · {mapSymbol.split('::').at(-1)}</button>}<TraceGraph onExplore={n => { setMode('map'); setMapSymbol(n.symbol_id); }} graph={(mode === 'trace' ? graph : overview) ?? { nodes: [], edges: [], paths: [] }} onNode={n => mode === 'map' && n.kind === 'file' ? setMapFile(n.file) : openNode(n, (mode === 'trace' ? graph : overview)?.version_key)} onEdge={edge => { setAssistantOpen(true); openEdge(edge, (mode === 'trace' ? graph : overview)?.version_key); }}/><div className="canvas-caption">{(mode === 'trace' ? graph : overview)?.message}<span>Supported static calls · not runtime behavior</span></div></>}
      </Suspense>
    </main>
    <aside className="companion" aria-label="Code companion"><div className="companion-heading"><h2 className="companion-title">Code companion</h2><button className="glass-button" onClick={() => input.current?.focus()}><MessageSquare size={14}/> Chat</button><button className="mobile-close icon-control" aria-label="Close companion" onClick={() => setAssistantOpen(false)}><X size={16}/></button></div>
      <div className="conversation" ref={conversation} aria-live="polite" aria-busy={busy}>
        <div className="repository-attachment"><span className="attachment-icon"><FileCode2 size={22}/></span><div><strong>{repo?.name ?? 'Your repository'}</strong><span>{manifest ? `${manifest.file_count} source files · ${version}` : 'Local source workspace'}</span></div></div>
        <div className="assistant-message introduction"><p>I can help you understand how your project fits together, follow its connections, and see what changed.</p><p>Open a file or ask a question. Every result links back to your source.</p><details><summary>How this works <ChevronDown size={12}/></summary><p>Search finds relevant code. Maps show supported static calls. Unsupported behavior stays unresolved. Your project is never executed.</p><p className="retrieval-config">{manifest?.retrieval ? <>Ranking: {manifest.retrieval.model ?? 'no embedding model'} · {manifest.retrieval.mode} · {manifest.retrieval.device.toUpperCase()}{manifest.retrieval.frozen_submission_configuration ? ' · frozen submission configuration' : ''}</> : manifest?.semantic.message}</p><label className="refinement-setting"><input type="checkbox" checked={agentic} onChange={e => setAgentic(e.target.checked)}/> Allow one retrieval refinement</label></details></div>
        {turns.map((turn,i) => <div className="conversation-turn" key={i}><div className="user-message">{turn.search?.query ?? `What changed from ${turn.comparison?.version_a} to ${turn.comparison?.version_b}?`}</div><div className="assistant-message">
          {turn.search && <><h3>{!turn.search.results.length ? 'No matching source found' : turn.search.match_basis === 'SEMANTIC_ONLY' ? 'Closest matches by meaning' : 'Here’s the relevant code'}</h3><p>{!turn.search.results.length ? 'Try a symbol name or a more specific description.' : turn.search.match_basis === 'SEMANTIC_ONLY' ? `No result shares a word or symbol with your question. These ${turn.search.results.length} snippets are only the nearest code by meaning and may be unrelated. Try a symbol name or more specific terms.` : `${turn.search.results.length} source matches in this snapshot, ranked in ${Math.max(1, Math.round(turn.search.latency_ms))} ms on CPU. Select a result to inspect the exact lines.`}</p><details className="reasoning"><summary>Investigation <ChevronDown size={12}/></summary>{turn.search.agent_trace.map((step,j) => <p key={j}><strong>{step.step.toLowerCase()}</strong> · {step.details}</p>)}</details><div className="source-matches">{turn.search.results.map(result => <button key={result.chunk_id} onClick={() => openResult(result,turn.search!.version_key)}><span className="file-badge">JS</span><span><strong>{result.rank}. {result.qualified_name}</strong><small>{result.file_path}:{result.start_line}–{result.end_line}</small><small>{result.evidence.exact_symbol_match ? 'Exact symbol · ' : ''}{result.evidence.lexical_rank ? `Lexical #${result.evidence.lexical_rank} · ` : ''}{result.evidence.semantic_rank ? `Semantic #${result.evidence.semantic_rank} · ` : ''}{result.evidence.structural_distance ? `${result.evidence.structural_distance} call hop(s)` : ''}</small></span><ArrowUpRight size={13}/></button>)}</div></>}
          {turn.search && <SequenceEvidence response={turn.search} onSource={(file,start,end,snapshot) => openFromCompanion(file,start,end,snapshot)}/>}
          {turn.comparison && <><h3>What changed between snapshots</h3><p>{turn.comparison.changes.modified_symbols.length} symbols modified, {turn.comparison.changes.added_symbols.length} added, and {turn.comparison.changes.removed_symbols.length} removed.</p><p>{turn.comparison.changes.added_edges.length} call sites added · {turn.comparison.changes.removed_edges.length} removed.</p><details open className="reasoning"><summary>Before & after <ChevronDown size={12}/></summary><div className="diff-evidence">{diffPair(turn.comparison).map((result,j) => result && <section key={j}><header><span className={`evidence-label ${j ? 'after' : 'before'}`}><i/>{j ? 'After' : 'Before'}</span><CopyCode text={result.snippet}/></header><CodeSnippet text={result.snippet}/><button className="source-link" onClick={() => openFromCompanion(result.file_path,result.start_line,result.end_line,j ? turn.comparison!.version_key_b : turn.comparison!.version_key_a)}>{result.file_path}:{result.start_line}<ArrowUpRight size={12}/></button></section>)}<footer><button className="glass-button" onClick={() => { setMode('changes'); setVersionA(turn.comparison!.version_a); setVersionB(turn.comparison!.version_b); setComparison(turn.comparison!); const id=turn.comparison!.changes.modified_symbols[0]; if(id) void showDiff(turn.comparison!,id); }}><GitCompareArrows size={13}/>Inspect change</button><span>Source verified <Check size={13}/></span></footer></div></details><details><summary>All changed symbols <ChevronDown size={12}/></summary>{Object.entries({ Added: turn.comparison.changes.added_symbols, Removed: turn.comparison.changes.removed_symbols }).map(([label,ids]) => <div key={label}><h4>{label}</h4>{ids.map(id => <p className="symbol-text" key={id}>{id}</p>)}</div>)}</details><small className="scope-note">Observed source changes, not a claim about the author’s intent.</small></>}
        </div></div>)}
        {selectedEdge && <div className="assistant-message edge-evidence"><h3>A supported connection</h3><p>This call resolves to a known definition in the indexed snapshot.</p><div className="evidence-code"><header><span className="evidence-label after"><i/>Call site</span><CopyCode text={selectedEdge.source_expression}/></header><CodeSnippet text={selectedEdge.source_expression}/></div><details open><summary>Source evidence <ChevronDown size={12}/></summary>{selectedEdge.supporting_spans?.map((span,i) => <button className="source-link" key={i} onClick={() => openFromCompanion(span.file_path,span.start_line,span.end_line,edgeSnapshot)}>{span.kind.replaceAll('_',' ')}<small>{span.file_path}:{span.start_line}</small><ArrowUpRight size={12}/></button>)}</details></div>}
        {busy && <div className="loading-evidence" role="status"><FlowMark loading/><strong>Analyzing your code…</strong><span>Reading source and checking supported relationships.</span></div>}
        {!busy && <div className="suggestion-area"><p>What would you like to understand?</p><div className="suggestions"><button disabled={!ready} onClick={() => explainCurrent()}>Find related code</button><button disabled={!ready} onClick={() => switchView('map')}>Explore connections</button><button disabled={!ready} onClick={() => switchView('changes')}>See what changed</button></div></div>}
        {!!overview?.unresolved?.length && <details className="unresolved-note"><summary title="Calls the static analyser could not trace to a definition in this snapshot — native APIs, external libraries, or dynamic dispatch">Unresolved calls · {overview.unresolved_count ?? overview.unresolved.length} <span className="unresolved-hint">(external / dynamic)</span><ChevronDown size={12}/></summary><p className="unresolved-desc">These calls couldn't be traced to a definition in the indexed snapshot — they may be native APIs, third-party libraries, or dynamic calls. Click any to jump to its location.</p>{overview.unresolved.map((call,i) => <button className="source-link" key={i} onClick={() => openFromCompanion(call.file,call.line,call.end_line,overview.version_key)}><span>{call.expression}<small>{call.reason}</small></span></button>)}</details>}
      </div>
      <form className="composer" onSubmit={e => { e.preventDefault(); ask(); }}><textarea ref={input} aria-label="Ask about your code" placeholder="Ask a follow-up…" value={query} onChange={e => setQuery(e.target.value)} onKeyDown={e => { if(e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); ask(); } }}/><div className="composer-controls"><button className="glass-button square" type="button" aria-label="Open repository" onClick={() => setShowRepo(true)}><Plus size={16}/></button><button className="glass-button square" type="button" aria-label="Focus source context" disabled={!source} onClick={() => { setQuery(`Where is ${source?.path.split('/').at(-1)?.replace(/\.[^.]+$/,'')} used?`); input.current?.focus(); }}><Sparkles size={15}/></button><button className="glass-button square send-button" aria-label="Send question" type="submit" disabled={!query.trim() || !ready || busy}><ArrowUp size={17}/></button></div></form>
    </aside>
    {showRepo && <div className="dialog-shade" onClick={() => setShowRepo(false)}><section className="repo-modal" role="dialog" aria-modal="true" aria-label="Open repository" onClick={e => e.stopPropagation()}><div className="modal-header"><FlowMark/><h2>Open a repository</h2><button className="icon-control" aria-label="Close dialog" onClick={() => setShowRepo(false)}><X size={18}/></button></div><p>Your code stays local. ASTFLOW reads source without running your project.</p><form onSubmit={e => { e.preventDefault(); void indexRepository(draftPath,draftVersion); }}><label>Repository path<input autoFocus value={draftPath} onChange={e => setDraftPath(e.target.value)} placeholder="C:\projects\my-app"/></label><label>Snapshot<input value={draftVersion} onChange={e => setDraftVersion(e.target.value)} placeholder="working-tree, HEAD, or Git revision"/></label><button className="blue-button" disabled={!draftPath.trim() || !draftVersion.trim() || indexing}>Open & index</button></form><button className="text-control" disabled={!repo?.demo_path} onClick={() => { setDraftPath(repo?.demo_path ?? ''); setDraftVersion('working-tree'); }}>Use demo repository</button></section></div>}
  </div>;
}
export default App;
