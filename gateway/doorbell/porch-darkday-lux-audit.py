#!/usr/bin/env python3
"""Read-only effective lux and HA-General dusk helper metadata, no actuator writes."""
import subprocess,shlex,json,base64,time
SRC=r'''
from pathlib import Path
import json,sqlite3,yaml
P=Path("/config")
match=("jns_lighting_effective_lux","general_outdoor_lighting_on_lux",
       "general_lighting_lux_hysteresis","jns_porch_security_activation_lux",
       "external_security_lights_porch_pir","sun.sun")
registries=[
 ("core.entity_registry","entities"),
]
for name,key in registries:
 try:
  for e in json.loads((P/".storage"/name).read_text()).get("data",{}).get(key,[]):
   if any(k in str(e.get("entity_id","")) for k in match):
    print("REGISTRY",json.dumps({a:e.get(a) for a in ("entity_id","platform","disabled_by","name","original_name")}),flush=True)
 except Exception as ex:print("REGISTRY_ERR",type(ex).__name__,flush=True)
for p in [P/"configuration.yaml",P/"automations.yaml",*sorted((P/"packages").glob("*.yaml"))]:
 if not p.exists():continue
 try:
  s=p.read_text()
  if any(k in s for k in match):
   print("FILE_REFERENCES",p.name,[k for k in match if k in s],flush=True)
 except:pass
try:
 storage=json.loads((P/".storage"/"core.restore_state").read_text()).get("data",{})
 states=storage if isinstance(storage,list) else storage.get("states",[])
 for entry in states:
  s=entry.get("state",{}) if isinstance(entry,dict) else {}
  if any(k in s.get("entity_id","") for k in match):
   print("RESTORE",json.dumps({"entity":s.get("entity_id"),"state":s.get("state"),"last_updated":s.get("last_updated")}),flush=True)
except Exception as e:print("RESTORE_ERR",type(e).__name__,flush=True)
db=P/"home-assistant_v2.db"
if db.is_file():
 try:
  c=sqlite3.connect("file:"+str(db)+"?mode=ro",uri=True,timeout=2)
  for ent in ["sensor.jns_lighting_effective_lux","input_number.general_outdoor_lighting_on_lux",
    "input_number.general_lighting_lux_hysteresis","sun.sun"]:
   row=c.execute("""SELECT s.state,s.last_updated_ts FROM states s JOIN states_meta m ON s.metadata_id=m.metadata_id
    WHERE m.entity_id=? ORDER BY s.state_id DESC LIMIT 1""",(ent,)).fetchone()
   print("RECORDER",ent,json.dumps(row),flush=True)
  c.close()
 except Exception as e:print("RECORDER_ERR",type(e).__name__,str(e)[:120],flush=True)
print("LUX_READONLY_AUDIT_COMPLETE",flush=True)
'''
payload="exec(__import__('base64').b64decode("+repr(base64.b64encode(SRC.encode()).decode())+"))"
def ssh(command, timeout=12):
 p=subprocess.run(["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","nodeb",shlex.join(command)],
     capture_output=True,text=True,timeout=timeout)
 if p.returncode:raise RuntimeError(p.stderr[-180:])
 return json.loads(p.stdout)
d=ssh(["qm","guest","exec","905","--","docker","exec","homeassistant","python3","-c",payload],25)
for i in range(20):
 if d.get("exited"):break
 time.sleep(.5)
 d=ssh(["qm","guest","exec-status","905",str(d["pid"])],12)
print("GUEST_EXIT",d.get("exitcode"),flush=True)
print((d.get("out-data") or "")[:7000],flush=True)
print("GUEST_ERR",(d.get("err-data") or "")[:350],flush=True)
