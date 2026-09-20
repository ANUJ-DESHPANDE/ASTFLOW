import { useMemo, useState, useEffect } from 'react';
import { ReactFlow, Background, Controls, MarkerType, Position } from '@xyflow/react';
import type { ReactFlowInstance } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import type { GraphData, GraphEdge, GraphNode } from '../types';
import { GitBranch, Focus, RotateCcw, FileCode2 } from 'lucide-react';
import {layoutGraph,neighborhood} from './graphLayout';

export function TraceGraph({graph,onNode,onEdge,onExplore}:{graph:GraphData;onNode:(node:GraphNode)=>void;onEdge:(edge:GraphEdge)=>void;onExplore?:(node:GraphNode)=>void}){
 const [selected,setSelected]=useState(''),[query,setQuery]=useState(''),[depth,setDepth]=useState(1),[direction,setDirection]=useState('both'),[local,setLocal]=useState(false);
 const [flow,setFlow]=useState<ReactFlowInstance|null>(null);
 const signature=graph.version_key+':'+graph.nodes.map(n=>n.symbol_id).sort().join('|');
 useEffect(()=>{setSelected('');setLocal(false);setQuery('');},[signature]);
 const positions=useMemo(()=>layoutGraph(graph),[graph]);
 const nearby=useMemo(()=>selected?neighborhood(graph,selected,depth,direction):new Set<string>(),[graph,selected,depth,direction]);
 const matches=graph.nodes.filter(n=>(n.qualified_name+' '+n.file).toLowerCase().includes(query.toLowerCase()));
 const candidates=local&&selected?graph.nodes.filter(n=>nearby.has(n.symbol_id)):graph.nodes;
 const shown=[...candidates].sort((a,b)=>Number(b.symbol_id===selected)-Number(a.symbol_id===selected)||Number(nearby.has(b.symbol_id))-Number(nearby.has(a.symbol_id))||a.symbol_id.localeCompare(b.symbol_id)).slice(0,60);
 const visible=new Set(shown.map(n=>n.symbol_id));
 const relevantEdges=graph.edges.map((edge,i)=>({edge,i})).filter(({edge})=>visible.has(edge.source)&&visible.has(edge.target));
 const nodes=shown.map(n=>({id:n.symbol_id,position:positions.get(n.symbol_id)!,sourcePosition:Position.Bottom,targetPosition:Position.Top,
  data:{label:<><span className="graph-node-kind">{n.kind}</span><strong>{n.qualified_name}</strong><span className="graph-node-file">{n.file}:{n.start_line}</span></>},
  style:{width:260,height:84,background:'#1b211c',color:'#ddd',border:`1px solid ${n.symbol_id===selected?'#7de3ac':'#526451'}`,borderRadius:8,textAlign:'left' as const,padding:'10px 12px',opacity:selected&&!nearby.has(n.symbol_id)?.25:1}}));
 const edges=relevantEdges.slice(0,250).map(({edge:e,i})=>({id:String(i),source:e.source,target:e.target,type:'smoothstep',markerEnd:{type:MarkerType.ArrowClosed,color:'#54cbb8'},style:{stroke:e.source===selected?'#54cbb8':e.target===selected?'#d0ad70':'#58796c',strokeWidth:e.source===selected||e.target===selected?2:1,opacity:selected&&!(nearby.has(e.source)&&nearby.has(e.target))?.15:.8},interactionWidth:28}));
 const current=graph.nodes.find(n=>n.symbol_id===selected);
 function center(id:string){setSelected(id);const p=positions.get(id);if(p)requestAnimationFrame(()=>flow?.setCenter(p.x+130,p.y+42,{zoom:1,duration:matchMedia('(prefers-reduced-motion: reduce)').matches?0:180}));}
 useEffect(()=>{const timer=setTimeout(()=>void flow?.fitView({padding:.15}),50);return()=>clearTimeout(timer);},[signature,local,depth,direction,flow]);
 if(!graph.nodes.length)return <div className="workspace-empty"><GitBranch size={28}/><h3>No supported relationships yet</h3><p>{graph.message??'Choose a file or trace a supported symbol pair.'}</p></div>;
 return <section className="graph-explorer" aria-label="Source-backed call graph"><div className="graph-controls"><input aria-label="Search graph nodes" placeholder="Find a node…" value={query} onChange={e=>setQuery(e.target.value)}/><button className="glass-button" title="Fit to screen" aria-label="Fit graph" onClick={()=>void flow?.fitView({padding:.15})}><Focus size={14}/></button><button className="glass-button" aria-label="Reset graph" onClick={()=>{setSelected('');setLocal(false);setDepth(1);setDirection('both');setQuery('');void flow?.fitView({padding:.15});}}><RotateCcw size={13}/></button></div>
 {query&&<div className="graph-matches">{matches.slice(0,20).map(n=><button key={n.symbol_id} onClick={()=>{center(n.symbol_id);setQuery('');}}>{n.qualified_name}<small>{n.file}</small></button>)}{!matches.length&&<span>No matching node in this view.</span>}</div>}
 <div className="trace-canvas"><ReactFlow key={signature} nodes={nodes} edges={edges} onInit={setFlow} fitView minZoom={.15} maxZoom={1.5} nodesDraggable={false} nodesConnectable={false} colorMode="dark" onNodeClick={(_,n)=>center(n.id)} onNodeDoubleClick={(_,n)=>onNode(graph.nodes.find(x=>x.symbol_id===n.id)!)} onEdgeClick={(_,edge)=>onEdge(graph.edges[Number(edge.id)])}><Background color="#2b302b" gap={22} size={1}/><Controls showInteractive={false}/></ReactFlow></div>
 {current&&<div className="graph-selection"><strong>{current.qualified_name}</strong><small>{current.file} · {graph.edges.filter(e=>e.target===selected).length} incoming / {graph.edges.filter(e=>e.source===selected).length} outgoing in view</small><div><button className="glass-button" onClick={()=>onNode(current)}><FileCode2 size={13}/>{current.kind==='file'?'Explore file':'Open source'}</button>{current.kind!=='file'&&onExplore&&<button className="glass-button" onClick={()=>onExplore(current)}>Explore calls</button>}<button className="glass-button" onClick={()=>setLocal(v=>!v)}>{local?'Show context':'Hide unrelated'}</button><select aria-label="Neighborhood depth" value={depth} onChange={e=>setDepth(Number(e.target.value))}>{[1,2,3].map(n=><option key={n} value={n}>{n} hop{n>1?'s':''}</option>)}</select><select aria-label="Call direction" value={direction} onChange={e=>setDirection(e.target.value)}><option value="both">Both directions</option><option value="incoming">Callers</option><option value="outgoing">Callees</option></select></div></div>}
 <div className="graph-key"><span>Caller → callee · green: outgoing · gold: incoming</span><span>{shown.length}/{graph.nodes.length} nodes · {Math.min(250,relevantEdges.length)}/{graph.edges.length} edges{graph.nodes[0]?.kind==='file'?' · file edges summarize call sites':''}</span>{(shown.length<graph.nodes.length||relevantEdges.length>250)&&<span>View limited. Search a node and explore its neighborhood.</span>}</div></section>;
}
