#!/usr/bin/env python3
import base64,json,shlex,subprocess,time
SRC=r'''
from pathlib import Path
import json,yaml,sqlite3,datetime
P=Path("/config")
a=yaml.safe_load((P/"automations.yaml").read_text())
c=next(x for x in a if str(x.get("id"))=="1791918795028")
blob=json.dumps(c,default=str)
ids=["binary_sensor.outdoor_raining","sensor.jns_lighting_effective_lux",
"sensor.0xa4c1383917c90309_illuminance","sensor.0xa4c1383917c90309_outdoor_lux_10_minute_average",
"weather.forecast_home","weather.ha_general","sun.sun","automation.general_shared_lux_progressive_control"]
db=sqlite3.connect("file:"+str(P/"home-assistant_v2.db")+"?mode=ro",uri=True,timeout=4)
out={}
for eid in ids:
 row=db.execute("""SELECT s.state,s.last_updated_ts FROM states s JOIN states_meta m ON s.metadata_id=m.metadata_id
 WHERE m.entity_id=? ORDER BY s.state_id DESC LIMIT 1""",(eid,)).fetchone()
 if row:
  st,ts=row;out[eid]={"state":st,"age_s":datetime.datetime.now(datetime.timezone.utc).timestamp()-ts if ts else None}
db.close()
checks={
"controller_enabled":out.get("automation.general_shared_lux_progressive_control",{}).get("state")=="on",
"repair_tag":"JNS_LUX_WEATHER_DUSK_REPAIR_V2" in str(c.get("description","")),
"priority_preserved":"JNS_LUX_PRIORITY_LADDER_V1" in str(c.get("description","")),
"rain_available":out.get("binary_sensor.outdoor_raining",{}).get("state") in ("on","off"),
"effective_lux_numeric":str(out.get("sensor.jns_lighting_effective_lux",{}).get("state","")).replace(".","",1).isdigit(),
"met_available":out.get("weather.forecast_home",{}).get("state") not in (None,"unknown","unavailable"),
"openmeteo_available":out.get("weather.ha_general",{}).get("state") not in (None,"unknown","unavailable"),
"freshness_300":"<= 300" in blob,
"dusk_lock":"dusk_lock" in blob,
}
print("JNS_LUX_REPAIR_RUNTIME="+json.dumps({"checks":checks,"states":out},sort_keys=True),flush=True)
assert all(checks.values()),checks
'''
enc=base64.b64encode(SRC.encode()).decode()
code="exec(__import__('base64').b64decode("+repr(enc)+"))"
def ssh(argv):
 p=subprocess.run(["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","nodeb",shlex.join(argv)],capture_output=True,text=True,timeout=40)
 if p.returncode:raise RuntimeError(p.stderr[-500:])
 return json.loads(p.stdout)
d=ssh(["qm","guest","exec","905","--","docker","exec","homeassistant","python3","-c",code]);pid=d.get("pid")
for _ in range(80):
 if d.get("exited"):break
 time.sleep(.5);d=ssh(["qm","guest","exec-status","905",str(pid)])
print(d.get("out-data") or "")
if d.get("exitcode")!=0:raise SystemExit(d.get("exitcode") or 2)
