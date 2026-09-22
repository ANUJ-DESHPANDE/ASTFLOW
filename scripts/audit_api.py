import tempfile,json
from pathlib import Path
from backend.app.main import create_app
from backend.app.config import ROOT,Settings
from fastapi.testclient import TestClient

out=[]
with tempfile.TemporaryDirectory() as d:
 app=create_app(Settings(cache=Path(d)/'cache',semantic='off',ts_enrich=False));c=TestClient(app,raise_server_exceptions=False)
 def record(name,method,path,expected,**kwargs):
  r=getattr(c,method)(path,**kwargs);entry={'case':name,'method':method,'path':path,'expected':expected,'status':r.status_code,'pass':r.status_code==expected,'json':r.headers.get('content-type','').startswith('application/json')};out.append(entry);assert entry['pass'],entry
 record('health','get','/api/health',200)
 record('no indexed repository','post','/api/search',400,json={'query':'bluetooth'})
 record('missing repository','post','/api/index',404,json={'repo_path':str(Path(d)/'absent'),'background':False})
 repo=Path(d)/'empty';repo.mkdir();record('empty repository','post','/api/index',400,json={'repo_path':str(repo),'background':False})
 (repo/'python.py').write_text('def run(): return 1');record('Python outside product parser','post','/api/index',400,json={'repo_path':str(repo),'background':False})
 record('index demo','post','/api/index',200,json={'repo_path':str(ROOT/'examples/demo-repo'),'background':False})
 for path in ['/api/repository','/api/versions','/api/index/status','/api/map','/api/checkpoint']:record(path,'get',path,200)
 for q in ['', ' '*5, 'x'*2001]:record('invalid query','post','/api/search',422,json={'query':q})
 for q in ['x','qxzjvnonexistentidentifier','function normalizeInput(raw) {','openBluetoothSettings']:record('valid query '+q,'post','/api/search',200,json={'query':q})
 for k in [0,51,'invalid']:record('invalid top_k','post','/api/search',422,json={'query':'Bluetooth','top_k':k})
 record('valid exact source','get','/api/source',200,params={'path':'voice/VoiceHandler.js'})
 for path in ['../.env','C:/Windows/system.ini','voice\\VoiceHandler.js']:
  record('source path guard','get','/api/source',400 if '..' in path or '\\' in path else 404,params={'path':path})
 record('unknown symbol','get','/api/symbol/unknown',404)
 record('known symbol','get','/api/symbol/voice/VoiceHandler.js::VoiceHandler.handle',200)
 record('unknown version','post','/api/search',400,json={'query':'x','version':'missing'})
 record('unknown callable map','get','/api/map',404,params={'symbol':'unknown'})
 record('bounded symbol neighborhood','get','/api/map',200,params={'symbol':'voice/VoiceHandler.js::VoiceHandler.handle','depth':2})
 record('invalid neighborhood depth','get','/api/map',422,params={'symbol':'x','depth':99})
 record('unknown trace symbols neutral result','post','/api/trace',200,json={'source_symbol_id':'unknown','target_symbol_id':'other'})
 record('invalid trace depth','post','/api/trace',422,json={'source_symbol_id':'x','target_symbol_id':'y','max_depth':999})
 record('compare same immutable source','post','/api/compare',200,json={'query':'session','version_a':'working-tree','version_b':'working-tree'})
 app.state.index_lock.acquire()
 try:record('duplicate indexing lock','post','/api/index',409,json={'repo_path':str(ROOT/'examples/demo-repo')})
 finally:app.state.index_lock.release()
 record('host guard','get','/api/health',400,headers={'host':'evil.example'})
 record('origin guard','get','/api/repository',403,headers={'origin':'https://evil.example'})
 record('cross-site guard','get','/api/repository',403,headers={'sec-fetch-site':'cross-site'})
 record('oversized JSON body','post','/api/search',413,content='x'*20000,headers={'content-type':'application/json'})
 record('wrong content type','post','/api/search',415,content='{}',headers={'content-type':'text/plain'})
Path('docs/audit/api-probes.json').write_text(json.dumps(out,indent=2));print(len(out),'API probes passed')
