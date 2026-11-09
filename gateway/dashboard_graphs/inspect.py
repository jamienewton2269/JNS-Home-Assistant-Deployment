import base64, json, sys, time, pathlib, subprocess, importlib.util
sys.path.insert(0, 'gateway/arrival_lighting')
from readiness_probe import ssh_host

CORE = r'''
import pathlib,json,collections,yaml,os,sqlite3
R=pathlib.Path('/config')
files=list((R/'dashboards').glob('*.yaml'))+list((R/'lovelace').glob('*.yaml'))+list((R/'.storage').glob('lovelace*'))
files += [p for p in [R/'ui-lovelace.yaml'] if p.exists()]
def walk(x):
 if isinstance(x,dict):
  t=x.get('type','')
  if isinstance(t,str) and ('chart' in t or 'graph' in t):
   safe={k:v for k,v in x.items() if k not in ('entities','entity','title','name','header','card_header','content') and isinstance(v,(str,int,float,bool,list))}
   es=x.get('entities',[x['entity']] if 'entity' in x else [])
   safe['entity_count']=len(es)
   safe['entity_option_keys']=sorted(set(k for e in es if isinstance(e,dict) for k in e))
   safe['domains']=sorted(set((e if isinstance(e,str) else e.get('entity','')).split('.')[0] for e in es if isinstance(e,(str,dict))))
   yield safe
  for v in x.values():yield from walk(v)
 elif isinstance(x,list):
  for v in x:yield from walk(v)
result=[]
for p in files:
 try:
  d=json.loads(p.read_text()) if p.parent.name=='.storage' else yaml.safe_load(p.read_text())
  cards=list(walk(d))
  if cards:result.append({'file':str(p.relative_to(R)),'cards':cards})
 except Exception:pass
resources=R/'.storage/lovelace_resources'
res=json.loads(resources.read_text()).get('data',{}).get('items',[]) if resources.exists() else []
js=[]
for p in (R/'www').rglob('*.js'):
 if any(s in str(p).lower() for s in ('statistics','graph-chart')):js.append({'path':str(p.relative_to(R)),'size':p.stat().st_size})
print(json.dumps({'graphs':result,'resources':[{'url':r.get('url'),'type':r.get('type')} for r in res], 'card_files':js, 'supervisor_token_available':bool(os.getenv('SUPERVISOR_TOKEN')),'components':[p.name for p in (R/'custom_components').iterdir() if p.is_dir()]}))
'''

def guest(vm,node,args):
 r=json.loads(ssh_host(node,['qm','guest','exec',str(vm),'--',*args]))
 pid=r.get('pid')
 for _ in range(50):
  if r.get('exited') or 'exitcode' in r:break
  if pid is None:raise RuntimeError('Guest response without completion or PID: '+str(list(r)))
  time.sleep(1)
  r=json.loads(ssh_host(node,['qm','guest','exec-status',str(vm),str(pid)]))
 if r.get('exitcode')!=0:raise RuntimeError('Guest failed: '+(r.get('err-data') or '')[-300:])
 if r.get('out-truncated'):raise RuntimeError('Guest output truncated')
 return r.get('out-data','')

for vm,node in [(905,'nodeb')]:
 code="exec(__import__('base64').b64decode('"+base64.b64encode(CORE.encode()).decode()+"'))"
 print('GRAPH_DETAIL',vm,guest(vm,node,['docker','exec','homeassistant','python3','-c',code]),flush=True)
 addons=json.loads(guest(vm,node,['ha','addons','list','--raw-json']))
 print('ADDON_LIST',vm,json.dumps([{k:x.get(k) for k in ('slug','name','state')} for x in addons.get('data',addons).get('addons',[])]),flush=True)
print('NODEC_MODULES',json.dumps({m:importlib.util.find_spec(m) is not None for m in ('aiohttp','websocket','websockets')}))
print('TOKEN_READABLE',pathlib.Path('/etc/jns/credentials/ha-general.token').is_file() and __import__('os').access('/etc/jns/credentials/ha-general.token',__import__('os').R_OK))
