import type { GraphData } from '../types';

/** Collapse cycles, then layer the resulting DAG. IDs decide all ties. */
export function layoutGraph(graph: GraphData): Map<string,{x:number;y:number}> {
 const ids=graph.nodes.map(n=>n.symbol_id).sort(), valid=new Set(ids);
 const next=new Map(ids.map(id=>[id,[] as string[]]));
 for(const e of graph.edges) if(valid.has(e.source)&&valid.has(e.target)) next.get(e.source)!.push(e.target);
 for(const list of next.values()) list.sort();
 let counter=0; const index=new Map<string,number>(),low=new Map<string,number>(),stack:string[]=[],active=new Set<string>(),groups:string[][]=[];
 function visit(id:string){index.set(id,counter);low.set(id,counter++);stack.push(id);active.add(id);
  for(const child of next.get(id)!){if(!index.has(child)){visit(child);low.set(id,Math.min(low.get(id)!,low.get(child)!));}else if(active.has(child))low.set(id,Math.min(low.get(id)!,index.get(child)!));}
  if(low.get(id)===index.get(id)){const group:string[]=[];let member:string;do{member=stack.pop()!;active.delete(member);group.push(member);}while(member!==id);groups.push(group.sort());}}
 for(const id of ids) if(!index.has(id))visit(id);
 groups.sort((a,b)=>a[0].localeCompare(b[0]));const groupOf=new Map<string,number>();groups.forEach((g,i)=>g.forEach(id=>groupOf.set(id,i)));
 const outgoing=groups.map(()=>new Set<number>()),incoming=groups.map(()=>0),level=groups.map(()=>0);
 for(const e of graph.edges){const a=groupOf.get(e.source),b=groupOf.get(e.target);if(a!==undefined&&b!==undefined&&a!==b&&!outgoing[a].has(b)){outgoing[a].add(b);incoming[b]++;}}
 const queue=groups.map((_,i)=>i).filter(i=>incoming[i]===0);
 while(queue.length){const current=queue.shift()!;for(const target of [...outgoing[current]].sort((a,b)=>a-b)){level[target]=Math.max(level[target],level[current]+1);if(--incoming[target]===0)queue.push(target);}queue.sort((a,b)=>a-b);}
 const layers=new Map<number,string[]>();groups.forEach((g,i)=>layers.set(level[i],[...(layers.get(level[i])??[]),...g]));
 const positions=new Map<string,{x:number;y:number}>();let y=0;
 for(const [,nodes] of [...layers].sort((a,b)=>a[0]-b[0])){nodes.sort();nodes.forEach((id,i)=>positions.set(id,{x:(i%4)*300,y:y+Math.floor(i/4)*120}));y+=Math.ceil(nodes.length/4)*120+50;}
 return positions;
}
export function neighborhood(graph:GraphData,id:string,depth:number,direction='both'){
 const seen=new Set([id]);let frontier=[id];
 for(let i=0;i<depth;i++){const next=new Set<string>();for(const e of graph.edges){if(direction!=='incoming'&&frontier.includes(e.source))next.add(e.target);if(direction!=='outgoing'&&frontier.includes(e.target))next.add(e.source);}frontier=[...next].filter(n=>!seen.has(n));frontier.forEach(n=>seen.add(n));}return seen;
}
