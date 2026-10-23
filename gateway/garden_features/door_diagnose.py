#!/usr/bin/env python3
"""Read-only diagnostics for VM905's Tuya back-door -> Zigbee Dogs Run path."""
import base64,json,time,sys
sys.path.insert(0,"gateway/arrival_lighting")
from readiness_probe import ssh_host
CORE=r"""
from pathlib import Path
import json, datetime, yaml, re
p=Path('/config'); st=p/'.storage'
wanted=[
 'binary_sensor.backdoor_contact_sensor_door',
 'switch.0x84fd27fffe9ce438',
 'timer.jns_backdoor_dogs_run',
 'input_number.jns_backdoor_dogs_run_minutes',
 'input_boolean.jns_backdoor_dogs_preexisting']
automation_ids=[
 'jns_backdoor_dogs_run_trigger_v1',
 'jns_backdoor_dogs_run_release_v1',
 '1792086505206',
 'jns_doorbell_security_release_20261020']
registry=json.loads((st/'core.entity_registry').read_text())['data']['entities']
r=[]
for e in registry:
  if e.get('entity_id') in wanted or e.get('unique_id') in automation_ids or any(k in e.get('entity_id','') for k in ('back_door_dogs_run','backdoor_dogs_run','backdoor_contact_sensor_door')):
    r.append({'entity_id':e.get('entity_id'),'platform':e.get('platform'),
              'disabled_by':e.get('disabled_by'),'unique_id':e.get('unique_id')})
cfg=yaml.safe_load((p/'packages/jns_garden_features_backdoor.yaml').read_text())
autos=cfg.get('automation',[])
a=[{'id':x.get('id'),'alias':x.get('alias'),
    'trigger':x.get('triggers'),'mode':x.get('mode')} for x in autos]
out={'package_exists':True,'registered_entities':r,'installed_automations':a}
tr=st/'trace.saved_traces'
out['trace_file_exists']=tr.exists()
if tr.exists():
 try:
  doc=json.loads(tr.read_text())
  results={}
  for typ, entries in doc.get('data',{}).items():
    if not isinstance(entries,dict):continue
    for aid,v in entries.items():
      if any(tag in str(aid) for tag in automation_ids):
        seq=v if isinstance(v,list) else [v]
        brief=[]
        for t in seq[-5:]:
          if not isinstance(t,dict):continue
          d={'last_step':t.get('last_step'),'state':t.get('state'),'script_execution':t.get('script_execution')}
          tm=t.get('timestamp',{})
          d['start_time']=tm.get('start') if isinstance(tm,dict) else None
          trace=t.get('trace',{})
          if isinstance(trace,dict):
            d['trace_step_paths']=list(trace)[-12:]
          brief.append(d)
        results[str(aid)]=brief
  out['matching_traces']=results
 except Exception as exc:out['trace_read_error']=type(exc).__name__
for fn in ('core.restore_state','trace.saved_traces'):
 fp=st/fn
 out[fn+'_size']=fp.stat().st_size if fp.exists() else None
restore=st/'core.restore_state'
if restore.exists():
 try:
  doc=json.loads(restore.read_text())
  arr=doc.get('data',[])
  if isinstance(arr,list):
   last={}
   for row in arr:
    if not isinstance(row,dict):continue
    ent=row.get('state',{})
    if isinstance(ent,dict) and ent.get('entity_id') in wanted:
      last[ent['entity_id']]={'state':ent.get('state'),'last_updated':ent.get('last_updated')}
   out['restored_state_cache']=last
 except Exception as exc:out['restore_read_error']=type(exc).__name__
# Check only existence/type, no secrets or private Tuya credentials.
entries=json.loads((st/'core.config_entries').read_text())['data']['entries']
out['tuya_entries']=[{'state':x.get('disabled_by'),'source':x.get('source')} for x in entries if x.get('domain')=='tuya']
out['recorder_backend_present']=(p/'home-assistant_v2.db').exists()
print(json.dumps(out,ensure_ascii=False))
"""
arg="exec(__import__('base64').b64decode("+repr(base64.b64encode(CORE.encode()).decode())+"))"
req=['qm','guest','exec','905','--','docker','exec','homeassistant','python3','-c',arg]
r=json.loads(ssh_host('nodeb',req))
pid=r.get('pid')
for i in range(65):
 if r.get('exited'):break
 if not isinstance(pid,int):raise RuntimeError('initial guest exec PID missing')
 time.sleep(1)
 r=json.loads(ssh_host('nodeb',['qm','guest','exec-status','905',str(pid)]))
if r.get('exitcode')!=0 or not r.get('exited'):
 print('BACKDOOR_DIAGNOSTIC_BLOCKED',str(r.get('err-data',''))[-700:]);raise SystemExit(2)
print('BACKDOOR_DIAGNOSTIC',r.get('out-data',''))
