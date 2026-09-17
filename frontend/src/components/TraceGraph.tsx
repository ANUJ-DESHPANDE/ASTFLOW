import { useMemo } from 'react';
import { ReactFlow, Background, Controls, MarkerType, Position } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import type { GraphData, GraphEdge, GraphNode } from '../types';
import { GitBranch } from 'lucide-react';

export function TraceGraph({ graph, onNode, onEdge }: { graph: GraphData; onNode: (node: GraphNode) => void; onEdge: (edge: GraphEdge) => void }) {
  const { nodes, edges } = useMemo(() => {
    const levels = new Map<string, number>();
    for (const path of graph.paths) path.forEach((id, index) => levels.set(id, Math.max(levels.get(id) ?? 0, index)));
    if (!levels.size) {
      const targets = new Set(graph.edges.map(e => e.target));
      const roots = graph.nodes.filter(n => !targets.has(n.symbol_id));
      let frontier = (roots.length ? roots : graph.nodes.slice(0, 1)).map(n => n.symbol_id);
      let depth = 0;
      while (frontier.length && depth < 6) {
        const next: string[] = [];
        for (const id of frontier) {
          if (levels.has(id)) continue;
          levels.set(id, depth);
          next.push(...graph.edges.filter(e => e.source === id && !levels.has(e.target)).map(e => e.target));
        }
        frontier = next; depth++;
      }
    }
    const slots = new Map<number, number>();
    const nodes = graph.nodes.map(n => {
      const level = levels.get(n.symbol_id) ?? 0;
      const slot = slots.get(level) ?? 0; slots.set(level, slot + 1);
      return { id: n.symbol_id, position: { x: slot * 310, y: level * 115 }, sourcePosition: Position.Bottom, targetPosition: Position.Top,
        data: { label: <><span className="graph-node-kind">{n.kind}</span><strong>{n.qualified_name}</strong><span className="graph-node-file">{n.file}:{n.start_line}</span></> },
        style: { width: 280, background: '#151c26', color: '#e3eaf2', border: '1px solid #3d6171', borderRadius: 8, textAlign: 'left' as const, padding: '12px 14px' } };
    });
    const edges = graph.edges.map((e, i) => ({ id: String(i), source: e.source, target: e.target,
      label: `L${e.call_line} · ${e.evidence_type === 'STATIC_VERIFIED' ? 'static' : 'language service'}`,
      markerEnd: { type: MarkerType.ArrowClosed, color: '#54cbb8' },
      style: { stroke: '#54cbb8', strokeWidth: 1.5 }, labelStyle: { fill: '#aebdcc', fontSize: 10 },
      labelBgStyle: { fill: '#10151d' }, interactionWidth: 28 }));
    return { nodes, edges };
  }, [graph]);
  if (!nodes.length) return <div className="empty-state compact"><GitBranch size={28}/><h3>No supported relationships yet</h3><p>Search for symbols or trace a supported pair to inspect source evidence.</p></div>;
  return <div className="trace-canvas" aria-label="Source-backed call graph">
    <ReactFlow nodes={nodes} edges={edges} fitView fitViewOptions={{ padding: .1 }} minZoom={.2} maxZoom={1.4}
      nodesDraggable={false} nodesConnectable={false} colorMode="dark"
      onNodeClick={(_, node) => onNode(graph.nodes.find(n => n.symbol_id === node.id)!)}
      onEdgeClick={(_, edge) => onEdge(graph.edges[Number(edge.id)])}>
      <Background color="#283340" gap={22} size={1}/><Controls showInteractive={false}/>
    </ReactFlow><div className="graph-legend"><span className="status-dot"/> Source-backed call edges <span>Click an edge to see its call site</span></div>
  </div>;
}
