#!/usr/bin/env python3
"""Read-only VM905 Recorder check for new native hallway and hourly forecast."""
import base64,importlib.util,json,pathlib
spec=importlib.util.spec_from_file_location("bridge",pathlib.Path("gateway/heating_presence/deploy.py"))
bridge=importlib.util.module_from_spec(spec);spec.loader.exec_module(bridge)
INNER=r"""
import sqlite3,pathlib,datetime,json
p=pathlib.Path('/config/home-assistant_v2.db')
assert p.is_file()
db=sqlite3.connect('file:'+str(p)+'?mode=ro',uri=True,timeout=6)
wanted=[
'sensor.jns_hallway_house_temperature',
'sensor.jns_fireplace_temperature',
'sensor.jns_hallway_hourly_open_meteo',
'sensor.jns_hallway_weather_input_status',
'binary_sensor.jns_fireplace_heat_detected',
'binary_sensor.jns_fireplace_override_safe']
result={}
now=datetime.datetime.now(datetime.timezone.utc).timestamp()
for eid in wanted:
 row=db.execute('SELECT s.state,s.last_updated_ts,a.shared_attrs FROM states s JOIN states_meta m ON s.metadata_id=m.metadata_id LEFT JOIN state_attributes a ON a.attributes_id=s.attributes_id WHERE m.entity_id=? ORDER BY s.state_id DESC LIMIT 1',(eid,)).fetchone()
 if row:
  state,ts,raw=row
  attrs=json.loads(raw or '{}')
  result[eid]={'seen':True,'state':state if 'weather' in eid or 'fireplace_override_safe' in eid else '[measurement]',
     'age_min':round((now-ts)/60,1) if ts else None,
     'hourly_points':attrs.get('total_hourly_points'),
     'forecast_horizon_valid':attrs.get('available_horizon'),
     'forecast_fetched':bool(attrs.get('fetched_at'))}
 else:result[eid]={'seen':False}
db.close()
print('JNS_HALLWAY_WEATHER_RECORDER '+json.dumps(result,sort_keys=True))
"""
def main():
 r=bridge.core(INNER,seconds=85)
 if r.get('exitcode')!=0:raise RuntimeError('Read-only weather recorder inspect failed')
 output=r.get('out-data') or ''
 if 'JNS_HALLWAY_WEATHER_RECORDER ' not in output:raise RuntimeError('Weather Recorder report missing')
 print(next(x for x in output.splitlines() if x.startswith('JNS_HALLWAY_WEATHER_RECORDER ')))
if __name__=='__main__':main()
