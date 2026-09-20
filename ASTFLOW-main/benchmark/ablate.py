"""Controlled local ablations. The demo labels are not a held-out test set."""
import copy,json,re,statistics,time
from pathlib import Path
from backend.app.agent.investigate import investigate
from backend.app.config import ROOT,Settings
from backend.app.indexing.service import IndexService
from backend.app.retrieval.search import Retriever
from backend.app.retrieval.embeddings import Embedder
from benchmark.metrics import metrics

def run():
    settings=Settings(cache=ROOT/'.astflow/ablation-cache',ts_enrich=False)
    service=IndexService(settings); service.embedder=Embedder(Settings())
    index=service.index(str(ROOT/'examples/demo-repo'))
    raw=copy.copy(index);raw.retriever=Retriever(index.chunks,index.retriever.embeddings,index.retriever.embedder,settings,tokenizer=lambda text:re.findall(r'\w+',text.lower()))
    queries=json.loads((ROOT/'benchmark/queries.json').read_text())
    variants=[('A BM25 (code tokens)',index,'bm25',False,False),('B Dense',index,'dense',False,False),('C Hybrid (plain tokens)',raw,'hybrid',False,False),('D Hybrid (code tokens)',index,'hybrid',False,False),('E Hybrid + symbol boosts',index,'full',False,False),('F Hybrid + symbol boosts + refinement',index,'full',True,False),('G Full ASTFLOW',index,'full',True,True),('G control: full without refinement',index,'full',False,True)]
    report={'scope':'16 curated demo queries; no held-out benefit claim','semantic':index.manifest['semantic'],'source_hash':index.manifest['source_hash'],'variants':{}}
    for name,idx,mode,agentic,structure in variants:
        if mode=='dense' and not index.manifest['semantic']['available']:
            report['variants'][name]={'status':'UNAVAILABLE'};continue
        details=[]
        for q in queries:
            response=investigate(idx,q['query'],'working-tree',50,agentic,mode,structure)
            details.append({'id':q['id'],**metrics([r['symbol_id'] for r in response['results']],q['relevant']),'latency_ms':response['latency_ms'],'passes':sum(t['step']=='SEARCH' for t in response['agent_trace'])})
        report['variants'][name]={'status':'MEASURED',**{k:statistics.mean(r[k] for r in details) for k in ['ndcg@10','mrr','latency_ms']},'queries':details}
    out=ROOT/'docs/audit/ablations.json';out.write_text(json.dumps(report,indent=2));print(json.dumps({k:{x:v[x] for x in v if x!='queries'} for k,v in report['variants'].items()},indent=2))
if __name__=='__main__':run()
