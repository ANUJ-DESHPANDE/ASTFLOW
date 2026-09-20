"""Official MTEB AppsRetrieval runner using ASTFLOW's real retrieval implementation.

Dataset qrels are consumed only by MTEB scoring, never by the search adapter.
Python corpus documents are retrieved as text; no JS graph or Python AST is claimed.
"""
import argparse
import hashlib
import importlib.metadata
import json
import sys
import time
import numpy as np
from pathlib import Path

if __package__ in {None, ''}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.config import ROOT, Settings
from backend.app.models.entities import Chunk
from backend.app.retrieval.embeddings import Embedder
from backend.app.retrieval.search import Retriever

MTEB_VERSION = '2.21.0'
DATASET_REVISION = 'f22508f96b7a36c2415181ed8bb76f76e04ae2d5'

class ASTFLOWSearch:
    def __init__(self, mode='bm25', download_model=False):
        from mteb.models.model_meta import ModelMeta
        self.mode = mode
        self.settings = Settings(semantic='off' if mode == 'bm25' else 'auto', ts_enrich=False)
        self.embedder = Embedder(self.settings)
        if mode != 'bm25' and self.embedder.load(download=download_model) is None:
            raise RuntimeError(self.embedder.reason + '; refusing to label lexical fallback as hybrid/dense')
        source = Path(__file__).read_bytes() + (ROOT/'backend/app/retrieval/search.py').read_bytes()
        revision = hashlib.sha256(source).hexdigest()[:16]
        self.mteb_model_meta = ModelMeta(name=f'ASTFLOW/{mode}', revision=revision, release_date=None,
            languages=['eng-Latn','python-Code'], loader=None, n_parameters=None, memory_usage_mb=None,
            max_tokens=None, embed_dim=None, license=None, open_weights=None, public_training_code=None,
            public_training_data=None, framework=[], similarity_fn_name=None, use_instructions=False,
            training_datasets=set(), model_type=['sparse'] if mode=='bm25' else ['dense'])
        self.measurements = {'mode':mode,'model':self.embedder.status,'query_latencies_ms':[],
                             'scope':'retrieval only; no graph, JS symbol boosts, or investigation agent'}

    def index(self, corpus, **kwargs):
        started=time.perf_counter()
        chunks=[]
        for row in corpus:
            did=str(row['id']); text='\n'.join([row.get('title',''),row['text']]).strip()
            chunks.append(Chunk(did,did,'',did,'dataset_document',1,max(1,len(text.splitlines())),text,text,hashlib.sha256(text.encode()).hexdigest()))
        chunks.sort(key=lambda c:c.chunk_id)
        if len({c.chunk_id for c in chunks}) != len(chunks):
            raise ValueError('Duplicate corpus IDs')
        vectors = None
        if self.mode != 'bm25':
            model_dir = self.settings.cache/'models'/self.settings.model.replace('/','--')
            weights = model_dir/'model.safetensors'
            model_hash = hashlib.sha256(weights.read_bytes()).hexdigest() if weights.exists() else self.settings.model
            identity = hashlib.sha256((model_hash+'\n'+'\n'.join(c.chunk_id+':'+c.content_hash for c in chunks)).encode()).hexdigest()
            vector_file=self.settings.cache/'datasets'/f'mteb-apps-{identity}.npy'
            if vector_file.exists():
                vectors=np.load(vector_file,allow_pickle=False)
                if vectors.ndim != 2 or len(vectors)!=len(chunks) or not np.isfinite(vectors).all():
                    raise ValueError('Invalid evaluation vector cache; remove it and retry')
            else:
                vectors=self.embedder.encode([c.text for c in chunks])
                vector_file.parent.mkdir(parents=True,exist_ok=True)
                np.save(vector_file,vectors,allow_pickle=False)
            self.measurements['embedding_weights_sha256']=model_hash
        self.retriever=Retriever(chunks,vectors,self.embedder,self.settings)
        self.measurements.update(corpus_count=len(chunks),index_seconds=time.perf_counter()-started,
            corpus_sha256=hashlib.sha256('\n'.join(c.chunk_id+':'+c.content_hash for c in chunks).encode()).hexdigest())

    def search(self, queries, *, top_k, top_ranked=None, **kwargs):
        if top_ranked is not None:
            raise ValueError('This adapter supports retrieval, not a prefiltered reranking task')
        results={}
        for i,row in enumerate(queries):
            started=time.perf_counter()
            text=row['text']
            if row.get('instruction'): text=row['instruction']+'\n'+text
            rows,_=self.retriever.rank(text,mode=self.mode,boosts=False,limit=top_k)
            results[str(row['id'])]={r['chunk'].chunk_id:float(r['score']) for r in rows[:top_k]}
            self.measurements['query_latencies_ms'].append((time.perf_counter()-started)*1000)
            if (i+1)%100==0: print(f'Retrieved {i+1} queries',flush=True)
        self.measurements['query_count']=len(results)
        self.measurements['ranking_depth']=top_k
        return results


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode',choices=['bm25','dense','hybrid'],default='bm25')
    parser.add_argument('--download-model',action='store_true')
    parser.add_argument('--output',type=Path,default=ROOT/'benchmark/results/mteb')
    args=parser.parse_args()
    if importlib.metadata.version('mteb') != MTEB_VERSION:
        raise RuntimeError(f'Install benchmark/requirements-mteb.txt (requires mteb=={MTEB_VERSION})')
    import mteb
    task=mteb.get_task('AppsRetrieval')
    if task.metadata.dataset['revision'] != DATASET_REVISION or task.metadata.eval_splits != ['test']:
        raise RuntimeError('Unexpected dataset revision/splits; review before evaluating')
    args.output.mkdir(parents=True,exist_ok=True)
    model=ASTFLOWSearch(args.mode,args.download_model)
    started=time.perf_counter()
    result=mteb.evaluate(model,[task],cache=None,overwrite_strategy='always',num_proc=1,
                         prediction_folder=args.output/'predictions',encode_kwargs={'batch_size':64})
    task_result=list(result.task_results)[0]
    task_result.to_disk(args.output/'appsretrieval_results.json')
    model.measurements.update(mteb_version=MTEB_VERSION,dataset_revision=DATASET_REVISION,
                              total_seconds=time.perf_counter()-started,official_mteb_run=True)
    (args.output/'run_metadata.json').write_text(json.dumps(model.measurements,indent=2),encoding='utf-8')
    print((args.output/'appsretrieval_results.json').read_text(encoding='utf-8'))

if __name__=='__main__':main()
