export type Evidence = {
  lexical_rank: number | null; semantic_rank: number | null; exact_symbol_match: boolean;
  structural_distance: number | null; structural_edges: GraphEdge[]; test_reference: boolean;
  relationship_status: string; contributions: Record<string, number>; semantic_score: number | null;
};
export type Result = {
  rank: number; chunk_id: string; symbol_id: string; symbol_name: string; qualified_name: string;
  kind: string; file_path: string; start_line: number; end_line: number; snippet: string;
  score: number; evidence: Evidence; version: string;
};
export type GraphNode = { symbol_id: string; qualified_name: string; file: string; start_line: number; end_line: number; kind: string };
export type GraphEdge = {
  source: string; target: string; call_file: string; call_line: number; call_end_line: number;
  source_expression: string; resolution_method: string; evidence_type: string; evidence_sources: string[];
  supporting_spans?: { file_path: string; start_line: number; end_line: number; kind: string }[];
};
export type GraphData = { nodes: GraphNode[]; edges: GraphEdge[]; paths: string[][]; status?: string; message?: string; version_key?: string;
  unresolved_count?: number; unresolved?: { file: string; line: number; end_line: number; expression: string; reason: string }[] };
export type SearchResponse = {
  query: string; version: string; version_key: string; results: Result[]; intent: string; latency_ms: number;
  /** What the result list rests on; SEMANTIC_ONLY means no result shares a word or symbol with the question. */
  match_basis?: 'KEYWORD_MATCH' | 'SEMANTIC_ONLY' | 'NONE';
  agent_trace: { step: string; details: string; data?: Record<string, unknown> }[];
  graph: GraphData; semantic: { available: boolean; message: string; model: string | null };
  sequences: { caller: string; before: string; after: string; file_path: string; before_line: number; after_line: number; explanation: string }[];
};
export type Manifest = {
  version: string; version_key: string; file_count: number; symbol_count: number; chunk_count: number; edge_count: number;
  index_latency_ms: number; indexed_at: string; semantic: { available: boolean; message: string };
  /** What ranks this snapshot's results (absent on indexes built before it was recorded). */
  retrieval?: { model: string | null; mode: string; device: string; frozen_submission_configuration: boolean };
  embedding_model?: string | null;
  enrichment: { status: string; edges_added: number; edges_confirmed: number }; warnings: string[];
};
export type Repository = { path: string | null; name: string | null; files: string[]; indexes: Manifest[]; demo_path: string };
export type Version = { name: string; label: string; indexed: boolean; commit: string | null; version_key: string | null };
export type Source = { path: string; version: string; version_key: string; content: string; full_content: string; start_line: number; end_line: number; total_lines: number };
export type IndexStatus = { state: string; stage: string; progress: number; manifest?: Manifest };
export type Changes = { added_symbols: string[]; removed_symbols: string[]; modified_symbols: string[]; added_edges: GraphEdge[]; removed_edges: GraphEdge[] };
export type Comparison = {
  query: string; version_a: string; version_b: string; version_key_a: string; version_key_b: string;
  results_a: Result[]; results_b: Result[]; changes: Changes; relevant_changes: Changes;
  rank_changes: { symbol_id: string; rank_a: number | null; rank_b: number | null; delta: number | null }[];
  graph_a: GraphData; graph_b: GraphData; latency_ms: number;
};
