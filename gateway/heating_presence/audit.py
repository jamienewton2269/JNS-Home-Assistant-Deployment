#!/usr/bin/env python3
"""Read-only heating/alarm/dashboard layout inspection on HA-General VM905."""
import sys,base64,json,time
sys.path.insert(0,'gateway/arrival_lighting')
from readiness_probe import ssh_host
CODE=r'''
import os,re,json,pathlib,yaml,hashlib
root=pathlib.Path('/config')
reg=json.loads((root/'.storage/core.entity_registry').read_text())['data']['entities']
def shortlist(e):
 return {'id':e.get('entity_id'),'platform':e.get('platform'),'disabled':e.get('disabled_by'),
   'name':str(e.get('name') or e.get('original_name') or '')[:90]}
entities=[shortlist(e) for e in reg if e.get('entity_id','').startswith('alarm_control_panel.') or
 (e.get('entity_id','').startswith(('input_select.','input_boolean.','input_number.','sensor.','climate.','script.')) and
 any(s in ' '.join([e.get('entity_id',''),str(e.get('name') or ''),str(e.get('original_name') or '')]).lower() for s in ('alarm','armed','away','home','thermostat','heat','base_temp','minimum')))]
out={'alarm_and_heating_entities':entities[:135]}
p=root/'.storage/lovelace_dashboards'
if p.exists():
 try:
  raw=json.loads(p.read_text())
  out['registered_dashboards']=[{'url_path':x.get('url_path'),'title':x.get('title'),'mode':x.get('mode'),'filename':x.get('filename')} for x in raw.get('data',{}).get('items',[])]
 except Exception as e:out['dashboard_registry_error']=str(type(e).__name__)
out['dashboard_yaml_files']=[str(x.relative_to(root)) for x in sorted((root/'dashboards').glob('*.yaml'))][:55]
out['lovelace_storage_files']=[x.name for x in sorted((root/'.storage').glob('lovelace*'))][:30]
src={}
for f in [root/'configuration.yaml',root/'automations.yaml',*(root/'packages').glob('*.yaml')]:
 try:lines=f.read_text().splitlines()
 except:continue
 rx=re.compile(r'(alarm_control_panel\.|climate\.set_temperature|heating.*(away|home|minimum|base)|min.*heating|predictive|input_boolean\.general_bedtime_mode|house.*temp|alarm.*(armed|disarmed))',re.I)
 hits=[{'line':i+1,'text':x[:190]} for i,x in enumerate(lines) if rx.search(x)]
 if hits:src[str(f.relative_to(root))]=hits[:22]
out['relevant_config_lines']=src
for f in [root/'dashboards/testing.yaml',root/'dashboards/heating.yaml',root/'dashboards/control.yaml',root/'dashboards/overview.yaml']:
 if f.is_file():
  lines=f.read_text().splitlines()
  src2=[{'line':i+1,'text':s[:200]} for i,s in enumerate(lines) if re.search(r'title:|path:|thermostat|climate\.|heating|bedtime|alarm',s,re.I)]
  out.setdefault('dashboard_sections',{})[str(f.relative_to(root))]=src2[:65]
# Existing entity registry can be stale; do not claim any current alarm state from this inventory.
print('JNS_HEAT_ALARM_DASH_AUDIT',json.dumps(out,default=str,sort_keys=True))
'''
def guest(cmd):
 r=json.loads(ssh_host('nodeb',['qm','guest','exec','905','--',*cmd]))
 for _ in range(35):
  if r.get('exited'):return r
  if not isinstance(r.get('pid'),int):raise RuntimeError('missing guest PID')
  time.sleep(1)
  r=json.loads(ssh_host('nodeb',['qm','guest','exec-status','905',str(r['pid'])]))
 raise RuntimeError('inspection timed out')
print('JNS_HEAT_ALARM_DASH_READONLY_BEGIN',flush=True)
assert 'running' in ssh_host('nodeb',['qm','status','905'])
encoded=base64.b64encode(CODE.encode()).decode()
r=guest(['docker','exec','homeassistant','python3','-c',"exec(__import__('base64').b64decode("+repr(encoded)+"))"])
print('JNS_HEAT_ALARM_DASH_READONLY_RESULT',(r.get('out-data') or '')[-26000:],flush=True)
if r.get('exitcode')!=0:raise RuntimeError('Read only inspection failed '+(r.get('err-data') or '')[-500:])
