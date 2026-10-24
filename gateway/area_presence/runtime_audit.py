#!/usr/bin/env python3
"""Read-only MQTT presence publication readiness: process uptime/config mtime/log counts."""
import base64,json,sys,time,shlex,subprocess
sys.path.insert(0,'gateway/arrival_lighting')
from readiness_probe import ssh_host

INSPECT=r"""
from pathlib import Path
import json,datetime
r=Path('/config')
base=[r/'configuration.yaml',r/'packages/jns_welcome_home.yaml',r/'custom_components/jns_native_area_sync/__init__.py']
out={'file_mtime_utc':{}}
for p in base:
 if p.exists():out['file_mtime_utc'][str(p.relative_to(r))]=datetime.datetime.fromtimestamp(p.stat().st_mtime,datetime.timezone.utc).isoformat()
log=r/'home-assistant.log'
from collections import deque
if log.exists():
 with log.open(errors='replace') as f:lines=deque(f,maxlen=30000)
 out['log_recent']={}
 for term in ('mqtt_statestream','jns_native_area_sync','jns_welcome_home','mqtt integration','MQTT connection','failed to set up','Setup failed'):
  found=[x for x in lines if term.lower() in x.lower()]
  out['log_recent'][term]={'count':len(found),'error_count':sum('ERROR' in x or 'WARNING' in x for x in found)}
print(json.dumps(out))
"""
def inspect(vm,node):
 cmd="exec(__import__('base64').b64decode('"+base64.b64encode(INSPECT.encode()).decode()+"'))"
 r=json.loads(ssh_host(node,['qm','guest','exec',str(vm),'--','docker','exec','homeassistant','python3','-c',cmd]))
 for i in range(45):
  if r.get('exited'):break
  pid=r.get('pid')
  if not isinstance(pid,int):raise RuntimeError('missing pid')
  time.sleep(1)
  r=json.loads(ssh_host(node,['qm','guest','exec-status',str(vm),str(pid)]))
 if r.get('exitcode')!=0 or not r.get('exited'):raise RuntimeError('inspect failed')
 core=ssh_host(node,['qm','guest','exec',str(vm),'--','docker','inspect','--format','{{.State.StartedAt}}','homeassistant'])
 q=json.loads(core)
 for i in range(45):
  if q.get('exited'):break
  time.sleep(1)
  q=json.loads(ssh_host(node,['qm','guest','exec-status',str(vm),str(q['pid'])]))
 return {'files':json.loads(r.get('out-data') or '{}'),'core_started_at':q.get('out-data','').strip() if q.get('exited') and q.get('exitcode')==0 else 'unavailable'}
for vm,node in [(902,'nodea'),(905,'nodeb')]:
 try: print('JNS_RUNTIME_AGE_VM'+str(vm),json.dumps(inspect(vm,node),sort_keys=True),flush=True)
 except Exception as exc:print('JNS_RUNTIME_AGE_VM'+str(vm)+'_BLOCKED',str(exc)[:230],flush=True)
try:
 test=ssh_host('nodeb',['pct','exec','212','--','timeout','7','mosquitto_sub','-h','mqtt-infra-a.home.arpa','-p','1883','-W','5','-C','1','-t','jns/site/areas/catalogue','-F','%t']).strip()
 print('JNS_BROKER_TOPIC_FORMAT_SUPPORT',test,flush=True)
except Exception as e: print('JNS_BROKER_TOPIC_FORMAT_SUPPORT_BLOCKED',str(e)[:250],flush=True)
