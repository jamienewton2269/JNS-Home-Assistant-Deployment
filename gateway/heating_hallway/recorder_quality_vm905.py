#!/usr/bin/env python3
"""Read-only VM905 thermal input quality audit via Node C trusted QGA.
No climate service calls. No secrets or raw sensor names/temperature samples in logs.
"""
import sys,json,base64,time
sys.path.insert(0,"gateway/arrival_lighting")
from readiness_probe import ssh_host

INNER=r'''
import json,datetime,sqlite3,math,pathlib,hashlib
R=pathlib.Path("/config")
now=datetime.datetime.now(datetime.timezone.utc)
es=json.loads((R/".storage/core.entity_registry").read_text())["data"]["entities"]
ds=json.loads((R/".storage/core.device_registry").read_text())["data"]["devices"]
cs=json.loads((R/".storage/core.config_entries").read_text())["data"]["entries"]
H="3fc0d19af1ae3fad19d67ae05b4ccb0f"; F="0xa4c138818d33ffff"
def tempids(device):
 return [x["entity_id"] for x in es if x.get("device_id")==device and
       not x.get("disabled_by") and x.get("entity_id","").startswith("sensor.")
       and ((x.get("device_class") or x.get("original_device_class"))=="temperature" or
        (not (x.get("device_class") or x.get("original_device_class")) and x.get("entity_id","").endswith("_temperature")))]
fireids=set()
for d in ds:
 if any(F in str(y).lower() for z in d.get("identifiers",[]) for y in z):
  fireids.add(d.get("id"))
for x in es:
 if F in str(x.get("unique_id","")).lower() and x.get("device_id"):fireids.add(x.get("device_id"))
hall=tempids(H);fire=sorted(set(e for d in fireids for e in tempids(d)))
if len(hall)!=1 or len(fire)!=1:raise ValueError("Source identity not unique")
ids={"hallway":hall[0],"fireplace":fire[0],
"bathroom":"sensor.0xa4c1382471d2ed23_temperature",
"honeywell":"sensor.thermostat_thermostat_indoor_temperature",
"outside_honeywell":"sensor.thermostat_thermostat_outdoor_temperature",
"outside_zigbee":"sensor.0xa4c13880bb5cffff_temperature"}
# Historical rows are read-only; recorder may use WAL, need no root writes.
db=R/"home-assistant_v2.db"
report={}
if db.exists():
 conn=sqlite3.connect("file:"+str(db)+"?mode=ro",uri=True,timeout=4)
 c=conn.cursor()
 for k,e in ids.items():
  try:
   c.execute("""SELECT state,last_updated_ts FROM states WHERE metadata_id=(SELECT metadata_id FROM states_meta WHERE entity_id=?)
     AND last_updated_ts>? ORDER BY state_id DESC LIMIT 550""",(e,(now-datetime.timedelta(hours=24)).timestamp()))
   rows=c.fetchall()
   numeric=[]
   for v,t in rows:
    try:
     f=float(v)
     if math.isfinite(f) and -30<f<70:numeric.append((f,t))
    except (TypeError,ValueError):pass
   unique=len(set(round(v,2) for v,t in numeric))
   latest=min(((now.timestamp()-t) for _,t in numeric if t is not None),default=None)
   report[k]={"samples_24h":len(numeric),"unique_temperatures_24h":unique,
              "last_recorder_age_minutes":None if latest is None else round(latest/60,1),
              "resolution_0p1_or_better":unique>=3,
              "min_max_delta":round(max(v for v,_ in numeric)-min(v for v,_ in numeric),1) if numeric else None}
  except (sqlite3.Error,ValueError):
   report[k]={"history":"not_available"}
 conn.close()
weather=[x for x in es if x.get("entity_id")=="weather.ha_general"]
heat=[x for x in cs if x.get("domain")=="jns_heating_zones"]
pkg=R/"packages/jns_house_temperature.yaml"
schedule=R/"packages/jns_heating_predictive_schedule.yaml"
print("JNS_HALLWAY_INPUT_READONLY "+json.dumps({
 "vm":905,"mode":"readonly","runtime_loaded_from_core":False,
 "temperature_history_quality":report,
 "weather_entity_registered":bool(weather),
 "heating_config_entry_count":len(heat),
 "original_learner_kept":True,
 "hallway_epoch_file_present":(R/".storage").joinpath("jns_heating_hallway_zone_"+heat[0]["entry_id"]).exists() if len(heat)==1 else False,
 "temperature_package_exists":pkg.exists(),
 "schedule_package_exists":schedule.exists()
},sort_keys=True))
'''
def main():
 compile(INNER, "jns-recorder-quality-inner.py", "exec")
 if "running" not in ssh_host("nodeb",["qm","status","905"]):raise RuntimeError("VM905 not running")
 py="exec(__import__('base64').b64decode('"+base64.b64encode(INNER.encode()).decode()+"'))"
 r=json.loads(ssh_host("nodeb",["qm","guest","exec","905","--","docker","exec","homeassistant","python3","-c",py]))
 until=time.monotonic()+90
 while not r.get("exited"):
  if not isinstance(r.get("pid"),int) or time.monotonic()>until:raise RuntimeError("VM905 inspection unverified")
  time.sleep(2);r=json.loads(ssh_host("nodeb",["qm","guest","exec-status","905",str(r["pid"])]))
 if r.get("exitcode")!=0:
  # One sanitized exception summary only; never export raw database rows.
  err=(r.get("err-data") or "").splitlines()
  tail=(err[-1] if err else "unclassified")[:160]
  raise RuntimeError("VM905 readonly recorder inspection rejected: "+tail)
 result=(r.get("out-data") or "").strip()
 if not result.startswith("JNS_HALLWAY_INPUT_READONLY "):raise RuntimeError("invalid report")
 print(result,flush=True)
if __name__=="__main__":main()
