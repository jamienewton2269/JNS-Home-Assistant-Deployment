import sys,pathlib,json,base64,time,os,shlex
sys.path.insert(0,'gateway/arrival_lighting')
from readiness_probe import ssh_host
HERE=pathlib.Path('gateway/dashboard_graphs')
def guest(args):
 r=json.loads(ssh_host('nodeb',['qm','guest','exec','905','--',*args]));pid=r.get('pid');until=time.monotonic()+180
 while not r.get('exited') and 'exitcode' not in r:
  if pid is None or time.monotonic()>until:raise RuntimeError('Guest completion unknown; inspect before retry')
  time.sleep(2);r=json.loads(ssh_host('nodeb',['qm','guest','exec-status','905',str(pid)]))
 return r
def core(source,*args):
 code="exec(__import__('base64').b64decode('"+base64.b64encode(source.encode()).decode()+"'))"
 r=guest(['docker','exec','homeassistant','python3','-c',code,*args])
 if r.get('exitcode')!=0:raise RuntimeError('Core staging/check failed: '+(r.get('err-data') or '')[-1000:])
 if r.get('out-truncated'):raise RuntimeError('Result truncated')
 return r.get('out-data','')
def main():
 runid=os.environ['GITHUB_RUN_ID'];assert runid.isdecimal()
 converter=(HERE/'convert_graphs.py').read_text()
 patch=(HERE/'migrate.py').read_text();patch=patch[patch.index('def patch_yaml('):patch.index('def main():')]
 source=converter+'\n'+patch+'\n'+(HERE/'stage_offline.py').read_text()
 print(core(source,runid),end='',flush=True)
 if '--apply' not in sys.argv:print('GRAPH_DRY_RUN_COMPLETE');return
 stage='/mnt/data/supervisor/homeassistant/.jns-backups/graph-card-'+runid
 stopped=False;applied=False
 try:
  r=guest(['ha','core','stop']);assert r.get('exitcode')==0,'Core stop failed'
  stopped=True;print('GRAPH_CORE_STOPPED',flush=True)
  r=guest(['sh','-c','test -z "$(docker ps --filter name=^/homeassistant$ --format \'{{.Names}}\')" && sh '+shlex.quote(stage+'/apply.sh')])
  assert r.get('exitcode')==0 and 'GRAPH_FILES_APPLIED' in r.get('out-data',''),'Graph apply failed'
  applied=True;print('GRAPH_FILES_APPLIED',flush=True)
 finally:
  if stopped:
   if not applied:guest(['sh',stage+'/rollback.sh'])
   r=guest(['ha','core','start']);assert r.get('exitcode')==0,'Core start failed; saved backups available'
   print('GRAPH_CORE_STARTED',flush=True)
 # Verify the stored configuration, resource, and actual HTTP asset after start.
 verify=r'''
import pathlib,json,hashlib,yaml,urllib.request,sys,time
R=pathlib.Path('/config');b=R/'.jns-backups'/('graph-card-'+sys.argv[1]);m=json.loads((b/'manifest.json').read_text());total=0
for x in m['files']:
 p=R/x['path'];raw=p.read_bytes();proposed=(b/'proposed'/str(m['files'].index(x))).read_bytes()
 if p.parent.name=='.storage':assert json.loads(raw)==json.loads(proposed),'Post-start storage differs'
 else:assert hashlib.sha256(raw).hexdigest()==x['new_sha'],'Post-start file differs'
 obj=json.loads(raw) if p.parent.name=='.storage' else yaml.safe_load(raw) if p.name!='configuration.yaml' else None
 if obj is not None:
  assert graph_count(obj,{'history-graph','statistics-graph'})==0
  if x['graphs']:total+=graph_count(obj,{CARD})
assert total>=sum(m['counts'].values())
for _ in range(30):
 try:
  for base in ('http://127.0.0.1','http://127.0.0.1:8123'):
   try:
    with urllib.request.urlopen(base+'/local/community/Statistics-Graph-Chart-Card/statistics-graph-chart-card.js',timeout=3) as r:asset=r.read();assert r.status==200
    break
   except Exception:continue
  else:raise RuntimeError('Asset not reachable')
  assert hashlib.sha256(asset).hexdigest()==m['card_sha256'];break
 except Exception:time.sleep(2)
else:raise RuntimeError('Graph resource not served after startup')
print('GRAPH_MIGRATION_VERIFIED',json.dumps({'graphs':sum(m['counts'].values()),'files':m['counts'],'card_http':200,'backup':str(b)}))
'''
 try:print(core(converter+'\n'+verify,runid),end='',flush=True)
 except Exception:
  print('GRAPH_POST_START_VERIFICATION_FAILED_ROLLING_BACK',flush=True)
  r=guest(['ha','core','stop']);assert r.get('exitcode')==0
  r=guest(['sh',stage+'/rollback.sh']);assert r.get('exitcode')==0
  r=guest(['ha','core','start']);assert r.get('exitcode')==0
  raise
if __name__=='__main__':main()
