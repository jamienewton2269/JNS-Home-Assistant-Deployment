#!/usr/bin/env python3
"""Hash-guarded native YAML Testing temperature view release, VM905 only.

No thermostat, heating package, thermal learner, security integration, VM power
or Core restart changes. The new view is appended to existing Testing YAML.
Uses native HA cards; no custom JS/resource installation. All private entity
identifiers remain inside HA-General; only safe metadata enters public CI logs.
"""
import base64
import json
import sys
import time
sys.path.insert(0, "gateway/arrival_lighting")
from readiness_probe import ssh_host

CORE = r'''
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,os,tempfile,stat,sys,yaml
ROOT=Path("/config")
D=ROOT/"dashboards"/"testing.yaml"
HALL_ID="3fc0d19af1ae3fad19d67ae05b4ccb0f"
FIRE_IEEE="0xa4c138818d33ffff"
HALL_HASH="0765c6b32aae"
FIRE_HASH="6e57b33c6d86"
def must(ok,reason):
 if not ok:raise RuntimeError(reason)
def sha(b):return hashlib.sha256(b).hexdigest()
must(D.is_file() and not D.is_symlink(),"Testing dashboard missing or symlink")
reg=json.loads((ROOT/".storage/core.entity_registry").read_text())["data"]["entities"]
dev=json.loads((ROOT/".storage/core.device_registry").read_text())["data"]["devices"]
enabled={x.get("entity_id") for x in reg if not x.get("disabled_by")}
def candidates(did):
 return sorted(set(x["entity_id"] for x in reg if x.get("device_id")==did
       and not x.get("disabled_by")
       and x.get("entity_id","").startswith("sensor.")
       and ((x.get("device_class") or x.get("original_device_class"))=="temperature"
            or (not x.get("device_class") and not x.get("original_device_class")
                and x.get("entity_id","").endswith("_temperature")))))
must(len([x for x in dev if x.get("id")==HALL_ID])==1,"Hallway identity mismatch")
hall=candidates(HALL_ID)
fires=set()
for x in dev:
 if any(FIRE_IEEE in str(z).lower() for pair in (x.get("identifiers") or []) for z in pair):
  fires.add(x.get("id"))
for x in reg:
 if FIRE_IEEE in str(x.get("unique_id","")).lower() and x.get("device_id"):fires.add(x["device_id"])
fire=sorted(set(z for did in fires for z in candidates(did)))
must(len(hall)==1 and sha(hall[0].encode()).startswith(HALL_HASH),"Hallway temperature not uniquely authenticated")
must(len(fire)==1 and sha(fire[0].encode()).startswith(FIRE_HASH),"Fireplace temperature not uniquely authenticated")
bath="sensor.0xa4c1382471d2ed23_temperature"
lyric="sensor.thermostat_thermostat_indoor_temperature"
outside="sensor.thermostat_thermostat_outdoor_temperature"
must(bath in enabled and lyric in enabled and outside in enabled,"Required original temperature entities missing")
plants=sorted({e["entity_id"] for e in reg if e.get("entity_id","").startswith("sensor.")
    and not e.get("disabled_by") and "temperature" in e.get("entity_id","")
    and any(k in e.get("entity_id","").lower() for k in ("plant","plot","grow","soil","moisture"))})
must(len(plants)<=16,"Unexpected plant entity count")
ext="sensor.0xa4c13880bb5cffff_temperature"
outdoor=[{"entity":outside,"name":"Honeywell outside"}]
if ext in enabled:outdoor.append({"entity":ext,"name":"External Zigbee"})
def line(e,n):return {"entity":e,"name":n}
house=[line(hall[0],"Hallway / house reference"),
       line(fire[0],"Living room fireplace"),line(bath,"Bathroom / monitor only"),
       line(lyric,"Honeywell measured"),
       line("sensor.jns_house_temperature_setpoint","Honeywell target")]
view={
 "title":"Temperature Trends", "path":"temperature-trends", "icon":"mdi:chart-areaspline",
 "cards":[
  {"type":"markdown","content":
     "## JNS House Temperature Trends\n"
     "**Live hallway:** {{ states('"+hall[0]+"') }} °C  · "
     "**Fireplace:** {{ states('"+fire[0]+"') }} °C  · "
     "**Honeywell:** {{ states('"+lyric+"') }} °C\n\n"
     "**Target:** {{ states('sensor.jns_house_temperature_setpoint') }} °C  · "
     "**Projected +60min:** {{ states('sensor.jns_house_predicted_60_minutes') }} °C\n\n"
     "These are live HA readings. Predictions may show unavailable until the "
     "new hallway-specific model is validated. This dashboard is monitoring-only."},
  {"type":"entities","title":"Current thermometers and forecast",
   "show_header_toggle":False,"entities":
      [line(hall[0],"Hallway • proposed house authority"),
       line(fire[0],"Fireplace"),line(bath,"Bathroom • display only"),
       line(lyric,"Honeywell measured"),
       line("sensor.jns_house_temperature_setpoint","Honeywell setpoint")]
      +outdoor
      +[line("sensor.jns_house_predicted_60_minutes","Existing forecast +60min"),
        line("sensor.lyric_home_heating_thermal_learning","Existing learning status")]},
  {"type":"history-graph","title":"House & thermostat • 24 hours",
   "hours_to_show":24,"refresh_interval":60,"entities":house},
  {"type":"history-graph","title":"House & thermostat • 7 days",
   "hours_to_show":168,"refresh_interval":60,"entities":house},
  {"type":"history-graph","title":"Outdoor weather • 7 days",
   "hours_to_show":168,"refresh_interval":60,"entities":outdoor},
  {"type":"history-graph","title":"Plant plots • 7 days",
   "hours_to_show":168,"refresh_interval":60,
   "entities":[line(p,"Plant temperature "+str(i+1)) for i,p in enumerate(plants)]}
      if plants else {"type":"markdown","content":"No plant-plot temperature entity is registered on HA-General."},
  {"type":"history-graph","title":"Recorded predictions when available • 24 hours",
   "hours_to_show":24,"refresh_interval":60,
   "entities":[line("sensor.jns_house_predicted_60_minutes",
                    "Prediction recorded at that time (+60m)")]}
  ]
}
raw=D.read_bytes()
original=yaml.safe_load(raw)
must(isinstance(original,dict) and isinstance(original.get("views"),list),
     "Testing dashboard root invalid")
must(list(original.keys())[-1]=="views","Views are not last root field: fail closed")
views=original["views"]
must(len(views)>=10 and len(views)<=100,"Unexpected Testing view count")
must(not any(x.get("path")=="temperature-trends" for x in views),"View already exists")
must(raw.count(b"views:")==1,"Ambiguous root views")
# Confirm file follows existing root-level '- title:' list style.
must(b"\n- title:" in raw,"Dashboard YAML uses unsupported list indentation")
append=yaml.safe_dump([view],sort_keys=False,allow_unicode=True,
                      default_flow_style=False,indent=2)
must(append.startswith("- title:"),"Generated view not a list item")
updated=raw.rstrip(b"\r\n")+b"\n"+append.encode()
new=yaml.safe_load(updated)
must(new["views"][:-1]==views and new["views"][-1]==view,
     "Unexpected modification to another Testing view")
report={"mode":"dry_run","vm":"905","new_view":"temperature-trends",
        "original_view_count":len(views),"new_view_count":len(new["views"]),
        "hallway_verified":True,"fireplace_verified":True,
        "plant_series":len(plants),"external_zigbee_visible":ext in enabled,
        "recorded_prediction_only":True,"thermostat_touched":False,
        "original_sha":sha(raw),"updated_sha":sha(updated)}
print("JNS_TRENDS_PRECHECK "+json.dumps(report,sort_keys=True),flush=True)
if "--apply" not in sys.argv:
 sys.exit(0)
backup_dir=ROOT/".jns-backups"/("hallway-temperature-trends-"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
backup_dir.mkdir(mode=0o700,parents=True,exist_ok=False)
backup=backup_dir/"testing.yaml"
backup.write_bytes(raw);backup.chmod(0o600)
must(backup.read_bytes()==raw and D.read_bytes()==raw,"Concurrent change / backup mismatch")
st=D.stat()
fd,tmp=tempfile.mkstemp(dir=str(D.parent),prefix=".jns-hallway-trends-")
try:
 with os.fdopen(fd,"wb") as f:
  f.write(updated);f.flush();os.fsync(f.fileno())
 os.chown(tmp,st.st_uid,st.st_gid);os.chmod(tmp,stat.S_IMODE(st.st_mode))
 must(D.read_bytes()==raw,"Concurrent edit before replacing dashboard")
 os.replace(tmp,D)
 must(sha(D.read_bytes())==sha(updated),"Written dashboard hash mismatch")
 must(yaml.safe_load(D.read_text())["views"][:-1]==views,
      "Existing Testing views differed after write")
except Exception:
 if D.exists() and sha(D.read_bytes())==sha(updated):
  D.write_bytes(raw)
 raise
finally:
 if os.path.exists(tmp):os.unlink(tmp)
print("JNS_TRENDS_APPLIED "+json.dumps({
 "vm":"905","view":"temperature-trends","new_view_count":len(new["views"]),
 "dashboard_old_sha":sha(raw),"dashboard_new_sha":sha(updated),
 "backup_verified":True,"no_core_restart":True,"no_heating_changes":True,
 "fireplace_override_unchanged":True
},sort_keys=True),flush=True)
'''
def core(flag):
  p=base64.b64encode(CORE.encode()).decode()
  cmd="exec(__import__('base64').b64decode('"+p+"'))"
  r=json.loads(ssh_host("nodeb",["qm","guest","exec","905","--",
       "docker","exec","homeassistant","python3","-c",cmd,flag]))
  deadline=time.monotonic()+110
  while not r.get("exited"):
    if not isinstance(r.get("pid"),int) or time.monotonic()>deadline:
      raise RuntimeError("HA General dashboard command completion unverified")
    time.sleep(2)
    r=json.loads(ssh_host("nodeb",["qm","guest","exec-status","905",str(r["pid"])]))
  output=r.get("out-data") or ""
  for line in output.splitlines():
    if line.startswith(("JNS_TRENDS_PRECHECK ","JNS_TRENDS_APPLIED ")):
      print(line,flush=True)
  if r.get("exitcode")!=0 or ("JNS_TRENDS_APPLIED " not in output and flag=="--apply"):
    raise RuntimeError("Dashboard "+flag+" failed or unverified")
def main():
  if "running" not in ssh_host("nodeb",["qm","status","905"]):
    raise RuntimeError("VM905 unavailable")
  core("--dry-run")
  core("--apply")
if __name__=="__main__":
  main()
