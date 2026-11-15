#!/usr/bin/env python3
import base64,json,shlex,subprocess,time
SRC=r'''
from pathlib import Path
import json
P=Path("/config")
def load(n,k):
    try:return json.loads((P/".storage"/n).read_text())["data"][k]
    except Exception:return []
ents=load("core.entity_registry","entities")
devs=load("core.device_registry","devices")
dm={d.get("id"):d for d in devs}
rows=[]
for e in ents:
    if not str(e.get("entity_id","")).startswith("light.") or e.get("disabled_by") is not None: continue
    d=dm.get(e.get("device_id"),{})
    rows.append({
      "entity_id":e.get("entity_id"),
      "entity_name":e.get("name") or e.get("original_name"),
      "platform":e.get("platform"),
      "created_at":e.get("created_at"),
      "modified_at":e.get("modified_at"),
      "device_name":d.get("name_by_user") or d.get("name"),
      "device_created":d.get("created_at"),
      "device_modified":d.get("modified_at"),
      "config_entry_id":e.get("config_entry_id"),
    })
print("JNS_ACTIVE_LIGHT_CREATION_MAP="+json.dumps(rows,sort_keys=True),flush=True)
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
