#!/usr/bin/env python3
"""Read-only HA Core startup diagnosis after Lux ladder install (no commands to devices)."""
import json,base64,sys,time
sys.path.insert(0,'gateway/arrival_lighting')
from readiness_probe import ssh_host
CODE=r'''
import pathlib,json,re,sqlite3,datetime,yaml
root=pathlib.Path('/config')
out={'package_exists':(root/'packages/jns_lux_priority_ladder.yaml').exists()}
try:
 cfg=(root/'configuration.yaml').read_text().splitlines()
 out['config_packages']=[{'line':i+1,'text':s[:180]} for i,s in enumerate(cfg) if 'packages:' in s or 'homeassistant:' in s or '!include' in s][:20]
except Exception as e:out['config_error']=str(type(e).__name__)
p=root/'home-assistant.log'
if p.exists():
 lines=p.read_text(errors='replace').splitlines()
 rx=re.compile('lux[_ -]priority|ladder|jns_lux_include|jns_lux_rank|failed to set up|invalid config|template|input_number|input_boolean|automation|error|warning',re.I)
 out['log_matches']=[x[:300] for x in lines if rx.search(x)][-95:]
else:out['log_exists']=False
try:
 reg=json.loads((root/'.storage/core.entity_registry').read_text())['data']['entities']
 out['registry_ladder']=[{'id':x.get('entity_id'),'unique_id':x.get('unique_id'),'disabled':x.get('disabled_by')} for x in reg if 'lux_ladder' in str(x.get('entity_id')) or 'lux_rank' in str(x.get('entity_id')) or 'lux_include_' in str(x.get('entity_id')) or x.get('unique_id')=='jns_lux_ladder_bootstrap_v1']
except Exception as e:out['registry_error']=type(e).__name__
db=root/'home-assistant_v2.db'
if db.exists():
 try:
  c=sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True,timeout=3)
  rows=c.execute("SELECT m.entity_id,s.state,s.last_updated_ts FROM states s JOIN states_meta m ON s.metadata_id=m.metadata_id WHERE m.entity_id LIKE 'input_boolean.jns_lux_%' OR m.entity_id LIKE 'input_number.jns_lux_%' OR m.entity_id LIKE 'automation.jns_lux_%' ORDER BY s.last_updated_ts DESC LIMIT 65").fetchall()
  out['recorder_states']=[{'id':x,'state':y} for x,y,t in rows[:40]]
  c.close()
 except Exception as e:out['sqlite_error']=type(e).__name__
print('JNS_LUX_LADDER_ERROR_DIAG '+json.dumps(out,default=str))
'''
def guest(args):
 r=json.loads(ssh_host('nodeb',['qm','guest','exec','905','--',*args]))
 for _ in range(40):
  if r.get('exited'):return r
  if not isinstance(r.get('pid'),int):raise RuntimeError('No QGA PID')
  time.sleep(1)
  r=json.loads(ssh_host('nodeb',['qm','guest','exec-status','905',str(r['pid'])]))
 raise RuntimeError('QGA timeout')
code="exec(__import__('base64').b64decode("+repr(base64.b64encode(CODE.encode()).decode())+"))"
r=guest(['docker','exec','homeassistant','python3','-c',code])
print((r.get('out-data') or '')[-21500:],flush=True)
if r.get('exitcode')!=0:raise RuntimeError('Diag failed '+(r.get('err-data') or '')[-200:])
