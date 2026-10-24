#!/usr/bin/env python3
"""Read-only VM905 host/Core health and optional recorder entity freshness."""
import base64,json,sys,time
sys.path.insert(0,"gateway/arrival_lighting")
from readiness_probe import ssh_host
GUEST=r'''
import datetime,json,os,pathlib,sqlite3,urllib.request
root=pathlib.Path("/config")
report={"recorder_found":False,"recorder_entities":{},"server_port_reachable":False}
for endpoint in ("http://127.0.0.1:8123/api/","http://localhost:8123/api/"):
 try:
  with urllib.request.urlopen(endpoint,timeout=3) as resp:
   report["server_port_reachable"]=True
   report["status_code"]=resp.status
 except Exception as e:
  code=getattr(e,"code",None)
  if code in (200,401,403):
   report["server_port_reachable"]=True
   report["status_code"]=code
  else:report.setdefault("port_errors",[]).append(type(e).__name__)
db=root/"home-assistant_v2.db"
if db.is_file():
 report["recorder_found"]=True
 try:
  con=sqlite3.connect("file:"+str(db)+"?mode=ro",uri=True,timeout=3)
  entities=["climate.thermostat_thermostat","binary_sensor.lyric_home_heating_heating_call",
  "sensor.lyric_home_heating_thermal_learning","sensor.lyric_home_heating_projected_temperature_in_60_minutes",
  "sensor.thermostat_thermostat_indoor_temperature"]
  for e in entities:
   rows=con.execute("""
    select s.state, s.last_updated_ts from states s
    join states_meta m on s.metadata_id=m.metadata_id
    where m.entity_id=? and s.last_updated_ts is not null
    order by s.last_updated_ts desc limit 1""",(e,)).fetchall()
   if rows:
    state,ts=rows[0]
    report["recorder_entities"][e]={"state":state,
      "age_minutes":round((datetime.datetime.now(datetime.timezone.utc).timestamp()-ts)/60,1)}
  con.close()
 except Exception as exc:report["recorder_error"]=type(exc).__name__
print(json.dumps(report,sort_keys=True))
'''
def guest(args,timeout=75):
 r=json.loads(ssh_host("nodeb",["qm","guest","exec","905","--",*args]))
 deadline=time.monotonic()+timeout
 while not r.get("exited"):
  if not isinstance(r.get("pid"),int) or time.monotonic()>deadline:raise RuntimeError("VM905 guest command timeout")
  time.sleep(1)
  r=json.loads(ssh_host("nodeb",["qm","guest","exec-status","905",str(r["pid"])]))
 return r
out={}
for label,command in [
 ("core_info",["ha","core","info","--raw-json"]),
 ("core_container",["docker","inspect","--format","{{.State.Status}} {{.State.Running}} {{.State.Restarting}}","homeassistant"]),
 ("core_status",["ha","core","stats","--raw-json"])]:
 try:
  response=guest(command,timeout=45)
  data=response.get("out-data","").strip()
  if label=="core_info" and data.startswith("{"):
   doc=json.loads(data)
   out[label]={k:doc.get(k) for k in ("version","version_latest","boot","port","ssl","state","watchdog","audio_input","audio_output","ip_address") if k in doc}
  elif label=="core_status" and data.startswith("{"):
   doc=json.loads(data)
   out[label]={k:doc.get(k) for k in ("memory_usage","memory_limit","cpu_percent") if k in doc}
  else:out[label]={"result":data[:200],"exitcode":response.get("exitcode")}
 except Exception as e:out[label]={"error":type(e).__name__}
encoded=base64.b64encode(GUEST.encode()).decode()
r=guest(["docker","exec","homeassistant","python3","-c",
 "exec(__import__('base64').b64decode('"+encoded+"'))"])
if r.get("exitcode")!=0:out["recorder_guest_failed"]=True
else:
 try:out["recorder"]=json.loads(r.get("out-data") or "{}")
 except Exception:out["recorder_output_invalid"]=True
print("JNS_HEATING_HAOS_READINESS "+json.dumps(out,sort_keys=True))
