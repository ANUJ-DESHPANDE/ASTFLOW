"""Official MTEB AppsRetrieval runner using ASTFLOW's real retrieval implementation.

Dataset qrels are consumed only by MTEB scoring, never by the search adapter.
Python corpus documents are retrieved as text; no JS graph or Python AST is claimed.
"""
import argparse
import subprocess
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
    def __init__(self, mode='bm25', download_model=False, model_name=None, precomputed=None):
        from mteb.models.model_meta import ModelMeta
        self.mode = mode
        # Vectors computed ahead of time by `final_retrieval.py embed` shards (same model, same text); verified below.
        self.precomputed = Path(precomputed) if precomputed else None
        self.settings = Settings(model=model_name or Settings().model, semantic='off' if mode == 'bm25' else 'auto', ts_enrich=False)
        self.embedder = Embedder(self.settings)
        if mode != 'bm25' and self.embedder.load(download=download_model) is None:
            raise RuntimeError(self.embedder.reason + '; refusing to label lexical fallback as hybrid/dense')
        source = (Path(__file__).read_bytes() + (ROOT/'backend/app/retrieval/search.py').read_bytes()
                  + (ROOT/'backend/app/retrieval/embeddings.py').read_bytes() + self.settings.model.encode())
        revision = hashlib.sha256(source).hexdigest()[:16]
        self.mteb_model_meta = ModelMeta(name=f'ASTFLOW/{mode}', revision=revision, release_date=None,
            languages=['eng-Latn','python-Code'], loader=None, n_parameters=None, memory_usage_mb=None,
            max_tokens=None, embed_dim=None, license=None, open_weights=None, public_training_code=None,
            public_training_data=None, framework=[], similarity_fn_name=None, use_instructions=False,
            training_datasets=set(), model_type=['sparse'] if mode=='bm25' else ['dense'])
        from backend.app.retrieval.embeddings import profile
        self.measurements = {'mode':mode,'model':self.embedder.status,'model_profile':profile(self.settings.model),'query_latencies_ms':[],
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
        if self.mode != 'bm25' and self.precomputed:
            vectors = self._precomputed_documents(chunks)
        elif self.mode != 'bm25':
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

    def _load(self, what):
        from benchmark.final_retrieval import load_shards
        ids, keys, matrix, per_item_ms, encode_s, shards = load_shards(self.precomputed, what)
        if matrix is None:
            raise ValueError(f'No precomputed {what} shards in {self.precomputed}')
        self.measurements[f'precomputed_{what}'] = {'items': len(ids), 'shards': shards, 'runner_seconds': encode_s,
            'per_item_ms_p50': float(np.median(per_item_ms)), 'per_item_ms_p95': float(np.percentile(per_item_ms, 95))}
        return ids, keys, matrix

    def _precomputed_documents(self, chunks):
        ids, keys, matrix = self._load('docs')
        by_id = {i: (k, v) for i, k, v in zip(ids, keys, matrix)}
        if len(by_id) != len(ids) or set(by_id) != {c.chunk_id for c in chunks}:
            raise ValueError('Precomputed documents do not cover the MTEB corpus exactly')
        if any(by_id[c.chunk_id][0] != c.content_hash for c in chunks):
            raise ValueError('Precomputed document text differs from the MTEB corpus text')
        vectors = np.stack([by_id[c.chunk_id][1] for c in chunks])
        probe = chunks[::max(1, len(chunks) // 4)][:4]  # live re-encode must reproduce the shard vectors
        live = self.embedder.encode([c.text for c in probe])
        cos = [float(a @ vectors[chunks.index(c)]) for a, c in zip(live, probe)]
        self.measurements['precomputed_probe_min_cos_docs'] = min(cos)
        if min(cos) < 0.995:  # alignment check; batch-padding noise measured at 7e-4 (gate run)
            raise ValueError(f'Precomputed document vectors do not match live encoding (min cos {min(cos):.4f})')
        _, qkeys, qmatrix = self._load('test')
        self.query_vectors = dict(zip(qkeys, qmatrix))
        return vectors

    def search(self, queries, *, top_k, top_ranked=None, **kwargs):
        if self.precomputed:
            from benchmark.final_retrieval import text_key
            from benchmark.e005_screen import QueryVectors
            texts = [(row['instruction'] + '\n' + row['text']) if row.get('instruction') else row['text'] for row in queries]
            missing = [t for t in texts if text_key(t) not in self.query_vectors]
            if missing:
                raise ValueError(f'{len(missing)} test queries have no precomputed vector')
            live = self.embedder.encode(texts[:3], kind='query')
            cos = [float(a @ self.query_vectors[text_key(t)]) for a, t in zip(live, texts[:3])]
            self.measurements['precomputed_probe_min_cos_queries'] = min(cos)
            if min(cos) < 0.995:  # alignment check; batch-padding noise measured at 7e-4 (gate run)
                raise ValueError(f'Precomputed query vectors do not match live encoding (min cos {min(cos):.4f})')
            self.retriever.embedder = QueryVectors({t: self.query_vectors[text_key(t)] for t in texts})
            self.measurements['query_latency_note'] = 'query_latencies_ms exclude query encoding (precomputed); see precomputed_test'
        if top_ranked is not None:
            raise ValueError('This adapter supports retrieval, not a prefiltered reranking task')
        results={}
        for i,row in enumerate(queries):
            started=time.perf_counter()
            text=row['text']
            if row.get('instruction'): text=row['instruction']+'\n'+text
            rows,_=self.retriever.rank(text,mode=self.mode,boosts=False,limit=top_k)
            # Emit strictly decreasing scores that encode ASTFLOW's own order. Raw RRF scores contain exact ties
            # (about 9% of queries tie inside the top 10), and MTEB/pytrec_eval re-sort ties by document id, i.e.
            # would score an order ASTFLOW never returns. Same convention as benchmark/verify_retrieval.py.
            ranked=rows[:top_k]
            results[str(row['id'])]={r['chunk'].chunk_id:float(len(ranked)-j) for j,r in enumerate(ranked)}
            self.measurements['query_latencies_ms'].append((time.perf_counter()-started)*1000)
            if (i+1)%100==0: print(f'Retrieved {i+1} queries',flush=True)
        self.last_results=results
        self.measurements['query_count']=len(results)
        self.measurements['ranking_depth']=top_k
        return results


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode',choices=['bm25','dense','hybrid'],default='bm25')
    parser.add_argument('--download-model',action='store_true')
    parser.add_argument('--diagnostics',action='store_true',help='Also record R@10/50/100 from the scored rankings')
    parser.add_argument('--precomputed',default=None,help='Directory of final_retrieval.py embed shards (docs-*, test-*)')
    parser.add_argument('--model',default=None,help='Dense model (default: the product default, ASTFLOW_MODEL or MiniLM)')
    parser.add_argument('--output',type=Path,default=ROOT/'benchmark/results/mteb')
    args=parser.parse_args()
    if importlib.metadata.version('mteb') != MTEB_VERSION:
        raise RuntimeError(f'Install benchmark/requirements-mteb.txt (requires mteb=={MTEB_VERSION})')
    import mteb
    task=mteb.get_task('AppsRetrieval')
    if task.metadata.dataset['revision'] != DATASET_REVISION or task.metadata.eval_splits != ['test']:
        raise RuntimeError('Unexpected dataset revision/splits; review before evaluating')
    args.output.mkdir(parents=True,exist_ok=True)
    git=lambda *a: subprocess.run(['git','-C',str(ROOT),*a],capture_output=True,text=True).stdout.strip()
    provenance={'git_commit':git('rev-parse','HEAD'),'git_dirty_files':git('status','--porcelain','--untracked-files=no').splitlines()}
    model=ASTFLOWSearch(args.mode,args.download_model,args.model,args.precomputed)
    started=time.perf_counter()
    result=mteb.evaluate(model,[task],cache=None,overwrite_strategy='always',num_proc=1,
                         prediction_folder=args.output/'predictions',encode_kwargs={'batch_size':64})
    task_result=list(result.task_results)[0]
    if args.diagnostics:
        # Hit@k (one relevant document per query) from the exact rankings MTEB scored, incl. @50 which MTEB does not report.
        from benchmark.e005_screen import load_dataset_split
        _, _, qrels = load_dataset_split('test')
        ranked = {q: sorted(r, key=r.get, reverse=True) for q, r in model.last_results.items()}
        model.measurements['diagnostic_recall'] = {f'r@{k}': sum(bool(set(ranked.get(q, [])[:k]) & set(rel)) for q, rel in qrels.items()) / len(qrels)
                                                   for k in (10, 50, 100)}
    task_result.to_disk(args.output/'appsretrieval_results.json')
    model.measurements.update(mteb_version=MTEB_VERSION,dataset_revision=DATASET_REVISION,
                              total_seconds=time.perf_counter()-started,official_mteb_run=True,**provenance)
    (args.output/'run_metadata.json').write_text(json.dumps(model.measurements,indent=2),encoding='utf-8')
    print((args.output/'appsretrieval_results.json').read_text(encoding='utf-8'))

if __name__=='__main__':main()
