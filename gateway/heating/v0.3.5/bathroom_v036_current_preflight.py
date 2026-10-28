#!/usr/bin/env python3
"""Read-only 0.3.6 install prerequisite check. VM905 Node B only."""
import base64,hashlib,json,pathlib,sys,time
sys.path.insert(0,"gateway/arrival_lighting")
from readiness_probe import ssh_host
ROOT=pathlib.Path("gateway/heating/v0.3.5")
inner=r'''
import hashlib,json,pathlib,sqlite3,datetime
root=pathlib.Path('/config')
comp=root/'custom_components/jns_heating_zones'
st=root/'.storage'
files=['manifest.json','__init__.py','coordinator.py','sensor.py','thermal.py','const.py','config_flow.py']
out={"files":{},"components_present":comp.is_dir(),"storage_present":st.is_dir(),
     "config_entries":[],"recorded_sensor_states":{}}
for file in files:
 p=comp/file
 if p.is_file():
  raw=p.read_bytes()
  out['files'][file]=hashlib.sha256(raw).hexdigest()
out['live_version']=json.loads((comp/'manifest.json').read_text()).get('version')
for e in json.loads((st/'core.config_entries').read_text())['data']['entries']:
 if e.get('domain')=='jns_heating_zones':
  out['config_entries'].append({'disabled':e.get('disabled_by'),'last_seven_id':e['entry_id'][-7:]})
out['separate_bathroom_store_present']=any(st.glob('jns_heating_bathroom_zone_*'))
try:
 con=sqlite3.connect('file:'+str(root/'home-assistant_v2.db')+'?mode=ro',uri=True,timeout=5)
 now=datetime.datetime.now(datetime.timezone.utc).timestamp()
 for name in ('sensor.0xa4c1382471d2ed23_temperature','sensor.0xa4c1382471d2ed23_humidity',
              'sensor.thermostat_thermostat_indoor_temperature',
              'binary_sensor.lyric_home_heating_heating_call','sensor.lyric_home_heating_thermal_learning'):
  row=con.execute('SELECT s.state,s.last_updated_ts FROM states s JOIN states_meta m ON s.metadata_id=m.metadata_id WHERE m.entity_id=? ORDER BY s.last_updated_ts DESC LIMIT 1',(name,)).fetchone()
  if row:out['recorded_sensor_states'][name]={"state":row[0],"state_change_age_minutes":round((now-row[1])/60,1)}
 con.close()
except Exception as exc:out['recorder_error']=type(exc).__name__
print(json.dumps(out,sort_keys=True))
'''
source="exec(__import__('base64').b64decode("+repr(base64.b64encode(inner.encode()).decode())+"))"
r=json.loads(ssh_host("nodeb",["qm","guest","exec","905","--","docker","exec","homeassistant","python3","-c",source]))
deadline=time.monotonic()+100
while not r.get('exited'):
 if not isinstance(r.get('pid'),int) or time.monotonic()>deadline:raise RuntimeError('VM905 preflight timeout')
 time.sleep(1)
 r=json.loads(ssh_host('nodeb',['qm','guest','exec-status','905',str(r['pid'])]))
if r.get('exitcode')!=0:raise RuntimeError('VM905 source preflight failed: '+str(r.get('err-data'))[-160:])
result=json.loads(r.get('out-data') or '{}')
need={'coordinator.py':hashlib.sha256((ROOT/'bathroom_extension/baseline/coordinator.py').read_bytes()).hexdigest(),
      'sensor.py':hashlib.sha256((ROOT/'bathroom_extension/baseline/sensor.py').read_bytes()).hexdigest()}
result['protected_source_matches_candidate_baseline']=all(result['files'].get(name)==digest for name,digest in need.items())
result['vm905_home_assistant_source_only']=True
print('JNS_BATHROOM_V036_PRODUCTION_PREFLIGHT',json.dumps(result,sort_keys=True))
