#!/usr/bin/env python3
import base64,json,shlex,subprocess,time
SRC=r'''
from pathlib import Path
import json,re,sqlite3,datetime
P=Path("/config")
def load(n,k):
    try:return json.loads((P/".storage"/n).read_text())["data"][k]
    except Exception:return []
ents=load("core.entity_registry","entities")
devs=load("core.device_registry","devices")
areas=load("core.area_registry","areas")
area_name={a.get("area_id"):a.get("name") for a in areas}
devmap={d.get("id"):d for d in devs}

active=[]
for e in ents:
    eid=e.get("entity_id","")
    if not eid.startswith(("light.","switch.")) or e.get("disabled_by") is not None: continue
    d=devmap.get(e.get("device_id"),{})
    area=e.get("area_id") or d.get("area_id")
    active.append({
      "entity_id":eid,
      "entity_name":e.get("name") or e.get("original_name"),
      "platform":e.get("platform"),
      "area_id":area,
      "area_name":area_name.get(area),
      "device_name":d.get("name_by_user") or d.get("name"),
      "device_id":e.get("device_id"),
      "config_entry_id":e.get("config_entry_id"),
    })
print("JNS_ACTIVE_LIGHT_SWITCH_MAP="+json.dumps(active,sort_keys=True),flush=True)

ids=["switch.0x84fd27fffe9ce438","switch.0xa4c138bda6ec8ea0",
     "binary_sensor.backdoor_contact_switch_contact","timer.jns_backdoor_dogs_run",
     "automation.jns_back_door_dogs_run_security_light"]
db=P/"home-assistant_v2.db"; out={}
if db.exists():
 c=sqlite3.connect("file:"+str(db)+"?mode=ro",uri=True,timeout=4);cur=c.cursor()
 for eid in ids:
  cur.execute("""SELECT s.state,s.last_updated_ts FROM states s
   JOIN states_meta m ON s.metadata_id=m.metadata_id
   WHERE m.entity_id=? ORDER BY s.state_id DESC LIMIT 15""",(eid,))
  out[eid]=[{"state":st,"time":datetime.datetime.fromtimestamp(ts,datetime.timezone.utc).isoformat() if ts else None}
            for st,ts in cur.fetchall()]
 c.close()
print("JNS_BACKDOOR_OUTPUT_HISTORY="+json.dumps(out,sort_keys=True),flush=True)
'''
enc=base64.b64encode(SRC.encode()).decode()
code="exec(__import__('base64').b64decode("+repr(enc)+"))"
def ssh(argv):
 p=subprocess.run(["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","nodeb",shlex.join(argv)],capture_output=True,text=True,timeout=40)
 if p.returncode: raise RuntimeError(p.stderr[-500:])
 return json.loads(p.stdout)
d=ssh(["qm","guest","exec","905","--","docker","exec","homeassistant","python3","-c",code]);pid=d.get("pid")
for _ in range(80):
 if d.get("exited"): break
 time.sleep(.5); d=ssh(["qm","guest","exec-status","905",str(pid)])
print(d.get("out-data") or "")
if d.get("exitcode")!=0:raise SystemExit(d.get("exitcode") or 2)
