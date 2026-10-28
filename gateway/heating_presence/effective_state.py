#!/usr/bin/env python3
"""Read-only VM905 verification: native alarm, learned bedtime, thermostat predictor states."""
import base64,json,sys,time
sys.path.insert(0,"gateway/arrival_lighting")
from readiness_probe import ssh_host
INNER=r'''
import json,pathlib,sqlite3,datetime,re
root=pathlib.Path('/config')
registry=json.loads((root/'.storage/core.entity_registry').read_text())['data']['entities']
ids=('alarm_control_panel.home_alarm','alarm_control_panel.house_alarm','sensor.jns_heating_verified_alarm_state',
'sensor.jns_heating_schedule_decision','sensor.jns_heating_predictive_preheat_minutes',
'sensor.jns_heating_predictive_cooling_minutes','sensor.jns_heating_learned_bedtime',
'input_boolean.jns_heating_automatic_override','input_number.jns_heating_away_minimum_temp',
'sensor.jns_house_temperature_setpoint','sensor.jns_house_temperature','input_number.jns_heating_bedtime_samples',
'automation.jns_heating_predictive_home_10am_and_learned_bedtime_setback')
out={'registered':[{'entity_id':x.get('entity_id'),'disabled':x.get('disabled_by'),'platform':x.get('platform')} for x in registry if x.get('entity_id') in ids]}
p=root/'packages/jns_ha_security_native_cutover_20261028_v2.yaml'
if p.exists():
 lines=p.read_text().splitlines()
 out['native_alarm_package_present']=True
 out['native_alarm_header']=[x[:125] for x in lines[:70] if re.match(r'^(alarm_control_panel:|  - platform:|    name:|    code_arm_required:)',x)]
else:out['native_alarm_package_present']=False
db=root/'home-assistant_v2.db'
if db.exists():
 try:
  conn=sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True,timeout=8)
  query="SELECT m.entity_id,s.state,s.last_updated_ts FROM states s JOIN states_meta m ON s.metadata_id=m.metadata_id WHERE m.entity_id IN ("+','.join('?' for _ in ids)+") ORDER BY s.last_updated_ts DESC LIMIT 90"
  rows=conn.execute(query,ids).fetchall()
  latest={}
  for eid,state,ts in rows:
   if eid not in latest:latest[eid]={'state':state,'updated_utc':datetime.datetime.fromtimestamp(ts,datetime.timezone.utc).isoformat() if ts else None}
  out['recorded_states']=latest
  conn.close()
 except Exception as e:out['recorder_status']=type(e).__name__
p=root/'.storage/core.restore_state'
if p.exists():
 try:
  j=json.loads(p.read_text())
  data=j.get('data')
  out['restore_state_type']=type(data).__name__
  if isinstance(data,dict):
   out['restore_state_keys']=list(data.keys())[:10]
   arr=data.get('states',[])
  elif isinstance(data,list):arr=data
  else:arr=[]
  restore=[]
  for row in arr:
   if not isinstance(row,dict):continue
   s=row.get('state',{})
   if isinstance(s,dict) and s.get('entity_id') in ids:restore.append({'id':s.get('entity_id'),'state':s.get('state')})
  out['restored_matching_states']=restore[:20]
 except Exception as e:out['restore_state_error']=type(e).__name__
print('JNS_HEATING_PRESENCE_EFFECTIVE_STATE',json.dumps(out,sort_keys=True))
'''
def guest(args):
 r=json.loads(ssh_host('nodeb',['qm','guest','exec','905','--',*args]))
 for _ in range(40):
  if r.get('exited'):return r
  if not isinstance(r.get('pid'),int):raise RuntimeError('Missing QGA pid')
  time.sleep(1)
  r=json.loads(ssh_host('nodeb',['qm','guest','exec-status','905',str(r['pid'])]))
 raise RuntimeError('QGA timeout')
src="exec(__import__('base64').b64decode("+repr(base64.b64encode(INNER.encode()).decode())+"))"
r=guest(['docker','exec','homeassistant','python3','-c',src])
out=r.get('out-data') or ''
print(out[-6000:],flush=True)
if r.get('exitcode')!=0:raise RuntimeError('Read-only state inspection failed '+str(r.get('err-data') or '')[-280:])
