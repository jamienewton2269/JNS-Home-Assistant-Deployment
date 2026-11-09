import json,sys,pathlib
from deploy_offline import guest,core
from convert_graphs import CARD
for args,label in [(['docker','inspect','-f','{{.State.Status}}','homeassistant'],'CORE_CONTAINER'),(['ha','core','info','--raw-json'],'CORE_INFO')]:
 r=guest(args)
 if label=='CORE_INFO' and r.get('exitcode')==0:
  d=json.loads(r.get('out-data','{}'));d=d.get('data',d);print(label,json.dumps({k:d.get(k) for k in ('state','version','port','ssl')}),flush=True)
 else:print(label,r.get('exitcode'),r.get('out-data','').strip(),flush=True)
verify=r'''
import pathlib,json,hashlib,yaml,urllib.request
R=pathlib.Path('/config');b=R/'.jns-backups/graph-card-42694708248';m=json.loads((b/'manifest.json').read_text());counts={}
for i,x in enumerate(m['files']):
 p=R/x['path'];raw=p.read_bytes();proposed=(b/'proposed'/str(i)).read_bytes()
 if p.parent.name=='.storage':assert json.loads(raw)==json.loads(proposed),'Stored dashboard changed'
 else:assert hashlib.sha256(raw).hexdigest()==x['new_sha'],'YAML changed'
 if x['graphs']:
  d=json.loads(raw) if p.parent.name=='.storage' else yaml.safe_load(raw)
  assert graph_count(d,{'history-graph','statistics-graph'})==0
  counts[x['path']]=graph_count(d,{CARD})
assets=[]
for base in ('http://127.0.0.1','http://127.0.0.1:8123'):
 try:
  with urllib.request.urlopen(base+'/local/community/Statistics-Graph-Chart-Card/statistics-graph-chart-card.js',timeout=5) as r:raw=r.read();status=r.status
  assert hashlib.sha256(raw).hexdigest()==m['card_sha256']
  assets.append({'base':base,'status':status,'bytes':len(raw)})
 except Exception as e:assets.append({'base':base,'error':type(e).__name__})
print('GRAPH_POST_START_AUDIT',json.dumps({'counts':counts,'total':sum(counts.values()),'assets':assets,'resources':json.loads((R/'.storage/lovelace_resources').read_text()).get('data') if (R/'.storage/lovelace_resources').exists() else 'YAML'}),flush=True)
assert any(a.get('status')==200 for a in assets),'Core graph asset not yet served'
'''
source=(pathlib.Path('gateway/dashboard_graphs/convert_graphs.py').read_text())+'\n'+verify
print(core(source),end='',flush=True)
