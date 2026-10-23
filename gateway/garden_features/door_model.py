#!/usr/bin/env python3
"""Read-only identify Tuya backdoor model and whether any open events recorded."""
import base64,json,time,sys
sys.path.insert(0,'gateway/arrival_lighting')
from readiness_probe import ssh_host
SCRIPT=r"""
from pathlib import Path
import json,sqlite3,datetime
root=Path('/config')
st=root/'.storage'
entities=json.loads((st/'core.entity_registry').read_text())['data']['entities']
devices={d.get('id'):d for d in json.loads((st/'core.device_registry').read_text())['data']['devices']}
target=next(e for e in entities if e.get('entity_id')=='binary_sensor.backdoor_contact_sensor_door')
device=devices.get(target.get('device_id'),{})
fields=['name','name_by_user','manufacturer','model','model_id','sw_version','hw_version','via_device_id','disabled_by','area_id']
d={key:device.get(key) for key in fields if device.get(key) is not None}
d['device_class']=target.get('device_class') or target.get('original_device_class')
d['entity_disabled_by']=target.get('disabled_by')
d['tuya_via_hub']=bool(device.get('via_device_id'))
db=sqlite3.connect('file:/config/home-assistant_v2.db?mode=ro',uri=True,timeout=8)
db.execute('PRAGMA query_only=ON')
e=target['entity_id']
counts=db.execute('''
 SELECT state,COUNT(*),max(last_updated_ts)
 FROM states s JOIN states_meta m ON s.metadata_id=m.metadata_id
 WHERE m.entity_id=? GROUP BY state
''',(e,)).fetchall()
sumry={}
for state,n,ts in counts:
 sumry[state]={'rows':n,'last_utc':datetime.datetime.fromtimestamp(ts,datetime.timezone.utc).isoformat() if ts else None}
db.close()
trace_path=st/'trace.saved_traces'
trace_meta={}
if trace_path.exists():
 try:
  trace=json.loads(trace_path.read_text())
  trace_meta={'top_level_keys':list(trace.keys()),'data_type':type(trace.get('data')).__name__}
  dat=trace.get('data')
  if isinstance(dat,dict):
    trace_meta['top_data_keys']=[str(k)[:90] for k in list(dat.keys())[:12]]
    for key,val in dat.items():
      if isinstance(val,dict):
        trace_meta['nested_type_'+str(key)]=list(val.keys())[:5]
      if isinstance(val,list):
        trace_meta['nested_type_'+str(key)]=['list_items',len(val)]
 except Exception as e:trace_meta={'error':type(e).__name__}
print(json.dumps({'tuya_device':d,'door_state_recorder_counts':sumry,'trace_file_shape':trace_meta},ensure_ascii=False))
"""
arg="exec(__import__('base64').b64decode("+repr(base64.b64encode(SCRIPT.encode()).decode())+"))"
resp=json.loads(ssh_host('nodeb',['qm','guest','exec','905','--','docker','exec','homeassistant','python3','-c',arg]))
pid=resp.get('pid')
for i in range(40):
 if resp.get('exited'):break
 if not isinstance(pid,int):raise RuntimeError('initial pid missing')
 time.sleep(1)
 resp=json.loads(ssh_host('nodeb',['qm','guest','exec-status','905',str(pid)]))
if not resp.get('exited') or resp.get('exitcode')!=0:
 print('BACKDOOR_DEVICE_AUDIT_BLOCKED',(resp.get('err-data') or '')[-500:]);raise SystemExit(2)
print('BACKDOOR_DEVICE_AUDIT',resp.get('out-data',''))
