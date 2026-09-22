"""Measured synthetic scale probes, not retrieval-quality benchmarks."""
import json,platform,statistics,tempfile,time
from pathlib import Path
import psutil
from backend.app.config import ROOT,Settings
from backend.app.indexing.service import IndexService
from backend.app.indexing.discovery import read_snapshot
from backend.app.parsing.javascript import parse_file
from backend.app.structure.resolver import resolve_structure
from backend.app.agent.investigate import investigate

def timed(fn):
    start=time.perf_counter();value=fn();return value,(time.perf_counter()-start)*1000

def main():
    report={'environment':{'platform':platform.platform(),'python':platform.python_version(),'cpu_count':psutil.cpu_count()},'scope':'Synthetic JS, semantic off, TS corroboration off. Phase probes execute separately; do not sum them into total. RSS is a snapshot, not peak. Timings include current machine contention.','scales':[]}
    with tempfile.TemporaryDirectory(prefix='astflow-scale-') as temporary:
        base=Path(temporary)
        for count in [10,100,1000]:
            repo=base/f'repo-{count}';repo.mkdir()
            for i in range(count):
                (repo/f'module{i:04}.js').write_text(f'export function start{i:04}(input){{return finish{i:04}(input);}}\nexport function finish{i:04}(input){{return input.trim();}}\n',encoding='utf-8')
            settings=Settings(cache=base/f'cache-{count}',semantic='off',ts_enrich=False)
            snapshot,read_ms=timed(lambda:read_snapshot(repo,'working-tree',settings))
            parsed,parse_ms=timed(lambda:[parse_file(p,s) for p,s in snapshot[0].items()])
            _,resolve_ms=timed(lambda:resolve_structure(parsed))
            service=IndexService(settings);index,index_ms=timed(lambda:service.index(str(repo)))
            _,cached_ms=timed(lambda:service.index(str(repo)))
            _,reload_ms=timed(lambda:IndexService(settings).get())
            timings=[]
            for _ in range(7):timings.append(investigate(index,'Where is start0001 called?','working-tree')['latency_ms'])
            (repo/'module0001.js').write_text('export function replacement(input){return input.toLowerCase();}',encoding='utf-8')
            updated,rebuild_ms=timed(lambda:service.index(str(repo)))
            row={'files':count,'symbols':len(index.symbols),'chunks':len(index.chunks),'source_bytes':sum(len(s.encode()) for s in index.files.values()),'read_ms':read_ms,'parse_ms':parse_ms,'resolve_ms':resolve_ms,'cold_index_ms':index_ms,'cached_index_ms':cached_ms,'cold_load_ms':reload_ms,'one_file_full_rebuild_ms':rebuild_ms,'search_median_ms':statistics.median(timings),'search_max_ms':max(timings),'rss_bytes':psutil.Process().memory_info().rss,'index_bytes':sum(p.stat().st_size for p in (settings.cache/'indexes'/index.manifest['version_key']).rglob('*') if p.is_file()),'snapshot_changed':index.manifest['version_key']!=updated.manifest['version_key']}
            report['scales'].append(row);print(json.dumps(row),flush=True)
    (ROOT/'docs/audit/performance.json').write_text(json.dumps(report,indent=2))
if __name__=='__main__':main()
