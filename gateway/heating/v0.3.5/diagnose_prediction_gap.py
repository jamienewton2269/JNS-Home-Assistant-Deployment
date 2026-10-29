#!/usr/bin/env python3
"""VM905 JNS Heating predictability audit; no writes or raw samples exported."""
import base64,json,sys,time
from pathlib import Path
sys.path.insert(0,"gateway/arrival_lighting")
from readiness_probe import ssh_host

candidate=(Path("gateway/heating/v0.3.5/thermal.py")).read_bytes()
INNER=r"""
import base64,hashlib,json,collections,datetime,pathlib,sys,types,sqlite3
home=pathlib.Path('/config')
comp=home/'custom_components'/'jns_heating_zones'
out={"live_version":json.loads((comp/'manifest.json').read_text()).get('version'),
     "source_digest":hashlib.sha256((comp/'thermal.py').read_bytes()).hexdigest(),
     "zones":[],"recorder":{},"forecast_config":{}}
def mod(n,src):
 m=types.ModuleType(n);sys.modules[n]=m;exec(compile(src,'<audit-'+n+'>','exec'),m.__dict__);return m
legacy=mod('_jns_old', (comp/'thermal.py').read_bytes())
candidate=mod('_jns_candidate',base64.b64decode(CANDIDATE_B64))
for p in sorted((home/'.storage').glob('jns_heating_zone_*')):
 raw=p.read_bytes();b=hashlib.sha256(raw).hexdigest()
 data=json.loads(raw).get('data',{})
 rows=data.get('samples',[])
 if not isinstance(rows,list):continue
 v0=legacy.ZoneLearner(rows).status()
 v1=candidate.ZoneLearner(rows).status()
 temp_levels=collections.Counter(str(x.get('indoor')) for x in rows if isinstance(x,dict))
 duty=collections.Counter('heated' if x.get('duty',0)>=.5 else 'idle' for x in rows if isinstance(x,dict))
 when=[]
 for x in rows:
  try:when.append(datetime.datetime.fromisoformat(x['at']))
  except Exception:pass
 now=datetime.datetime.now(datetime.timezone.utc)
 minage=round((now-max(when)).total_seconds()/60,1) if when else None
 out['zones'].append({
 'sample_count':len(rows),'sample_age_minutes':minage,
 'distinct_indoor_temp_values':len(temp_levels),
 'indoor_temp_histogram':temp_levels.most_common(8),
 'duty_split':duty,
 'legacy':{k:v0.get(k) for k in ('ready','samples','reason','loss_per_hour','heat_gain_c_per_hour','drift_c_per_hour')},
 'candidate':{k:v1.get(k) for k in ('ready','samples','reason','valid_windows','nonzero_delta_windows','heated_windows','unheated_windows','indoor_levels','clock_or_gap_rejections','short_5min_adjacent_pairs')},
 'storage_unchanged':hashlib.sha256(p.read_bytes()).hexdigest()==b})
forecast_code=(comp/'coordinator.py').read_text()
out['forecast_config']['retry_v2_present']='JNS_FORECAST_RETRY_V2' in forecast_code
out['forecast_config']['weather_entity_reference']='weather.ha_general'
db=home/'home-assistant_v2.db'
if db.exists():
 try:
  con=sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True,timeout=4)
  for entity in ('weather.ha_general','sensor.lyric_home_heating_thermal_learning','sensor.lyric_home_heating_projected_temperature_in_60_minutes','sensor.thermostat_thermostat_indoor_temperature','sensor.thermostat_thermostat_outdoor_temperature'):
   result=con.execute('SELECT s.state,s.last_updated_ts FROM states s JOIN states_meta m ON s.metadata_id=m.metadata_id WHERE m.entity_id=? ORDER BY s.last_updated_ts DESC LIMIT 1',(entity,)).fetchone()
   if result:
    state,ts=result
    out['recorder'][entity]={'state':state if entity!='weather.ha_general' else ('available' if state not in ('unknown','unavailable') else state),
                            'age_minutes':round((now.timestamp()-ts)/60,1) if ts else None}
  con.close()
 except Exception as exc:out['recorder_error']=type(exc).__name__
print(json.dumps(out,sort_keys=True))
"""
script=INNER.replace("CANDIDATE_B64",repr(base64.b64encode(candidate).decode()))
expr="exec(__import__('base64').b64decode('"+base64.b64encode(script.encode()).decode()+"'))"
res=json.loads(ssh_host("nodeb",["qm","guest","exec","905","--","docker","exec","homeassistant","python3","-c",expr]))
end=time.monotonic()+100
while not res.get("exited"):
 if not isinstance(res.get("pid"),int) or time.monotonic()>end:raise RuntimeError("heating learner audit did not finish")
 time.sleep(1)
 res=json.loads(ssh_host("nodeb",["qm","guest","exec-status","905",str(res["pid"])]))
if res.get("exitcode")!=0:
 print("JNS_HEATING_PREDICTION_AUDIT_BLOCKED",(res.get("err-data") or "")[-550:])
 raise SystemExit(2)
data=json.loads(res.get("out-data") or "{}")
if not data.get("zones"):raise RuntimeError("learning store missing")
if not all(x.get("storage_unchanged") for x in data["zones"]):raise RuntimeError("unexpected storage change")
print("JNS_HEATING_PREDICTION_AUDIT",json.dumps(data,sort_keys=True))
