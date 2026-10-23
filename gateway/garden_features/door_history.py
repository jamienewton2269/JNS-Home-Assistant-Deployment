#!/usr/bin/env python3
"""Read-only HA General recorder: verify Tuya backdoor changes and Dogs Run actions."""
import base64,json,time,sys
sys.path.insert(0,"gateway/arrival_lighting")
from readiness_probe import ssh_host
CORE=r"""
from pathlib import Path
import json,sqlite3,datetime
db=Path('/config/home-assistant_v2.db')
names=[
 'binary_sensor.backdoor_contact_sensor_door',
 'sensor.backdoor_contact_sensor_battery',
 'switch.0x84fd27fffe9ce438',
 'timer.jns_backdoor_dogs_run',
 'automation.jns_back_door_dogs_run_security_light',
 'automation.jns_back_door_release_dogs_run_security_light']
output={}
if not db.exists():
 print(json.dumps({'error':'recorder_db_not_found'}));raise SystemExit(1)
dbcon=sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True,timeout=8)
dbcon.execute('PRAGMA query_only=ON')
for entity in names:
 try:
  rows=dbcon.execute('''
 SELECT s.state,s.last_updated_ts,s.last_changed_ts
 FROM states_meta m JOIN states s ON s.metadata_id=m.metadata_id
 WHERE m.entity_id=? ORDER BY s.state_id DESC LIMIT 14''',(entity,)).fetchall()
  records=[]
  for state,ts,changed in rows:
   records.append({'state':state,'time_utc':datetime.datetime.fromtimestamp(ts,datetime.timezone.utc).isoformat() if ts else None,'changed_utc':datetime.datetime.fromtimestamp(changed,datetime.timezone.utc).isoformat() if changed else None})
  output[entity]=records
 except Exception as exc:output[entity]={'error':type(exc).__name__}
print(json.dumps({'history':output},sort_keys=True))
dbcon.close()
"""
arg="exec(__import__('base64').b64decode("+repr(base64.b64encode(CORE.encode()).decode())+"))"
req=['qm','guest','exec','905','--','docker','exec','homeassistant','python3','-c',arg]
res=json.loads(ssh_host('nodeb',req))
pid=res.get('pid')
for i in range(55):
 if res.get('exited'):break
 if not isinstance(pid,int):raise RuntimeError('no_initial_qga_pid')
 time.sleep(1)
 res=json.loads(ssh_host('nodeb',['qm','guest','exec-status','905',str(pid)]))
if not res.get('exited') or res.get('exitcode')!=0:
 print('BACKDOOR_HISTORY_BLOCKED',(res.get('err-data') or '')[-400:]);raise SystemExit(1)
print('BACKDOOR_HISTORY',res.get('out-data',''),flush=True)
