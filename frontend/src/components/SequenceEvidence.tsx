import type {SearchResponse} from '../types';

export function SequenceEvidence({response,onSource}:{response:SearchResponse;onSource:(file:string,start:number,end:number,version:string)=>void}) {
  if(response.intent !== 'SEQUENCE') return null;
  return <section className="sequence-evidence"><h4>Source order evidence</h4>
    {response.sequences.length ? response.sequences.map((item,i)=><div key={i}>
      <p>{item.before.split('::').at(-1)} → {item.after.split('::').at(-1)}</p>
      <p>{item.explanation}</p>
      <button className="source-link" onClick={()=>onSource(item.file_path,item.before_line,item.after_line,response.version_key)}>{item.file_path}:{item.before_line}–{item.after_line}</button>
    </div>) : <p>No supported lexical ordering was established for this query. Search matches alone do not prove execution order.</p>}
  </section>;
}
