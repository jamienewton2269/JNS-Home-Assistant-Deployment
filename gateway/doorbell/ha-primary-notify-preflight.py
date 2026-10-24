#!/usr/bin/env python3
"""Read-only staging preflight for HA-Primary VM902 minimal doorbell notification."""
import base64,json,shlex,subprocess,time
SRC=r'''
from pathlib import Path
import json,re,hashlib
P=Path("/config")
config=P/"configuration.yaml"
autos=P/"automations.yaml"
print("CONFIGURATION_TOP_LEVEL_DIRECTIVES",flush=True)
for i,line in enumerate(config.read_text().splitlines(),1):
 if re.match(r"^[A-Za-z_][^:]{0,50}:",line):
  print(i,line[:160],flush=True)
print("AUTOMATION_FILE",autos.exists(),"bytes",autos.stat().st_size if autos.exists() else None,flush=True)
if autos.exists():
 print("AUTOMATION_SHA256",hashlib.sha256(autos.read_bytes()).hexdigest(),flush=True)
 try:
  import yaml
  d=yaml.safe_load(autos.read_text())
  print("AUTOMATION_TYPE",type(d).__name__,"COUNT",len(d) if isinstance(d,list) else "N/A",flush=True)
 except Exception as e:print("AUTOMATIONS_PARSE_ERROR",type(e).__name__,flush=True)
print("YAML_LOVELACE_FILES",[p.name for p in (P/".storage").iterdir() if p.name.startswith("lovelace")][:35],flush=True)
for name,key in (("core.entity_registry","entities"),("core.config_entries","entries")):
 try:
  data=json.loads((P/".storage"/name).read_text())["data"].get(key,[])
  if name.startswith("core.entity"):
   for e in data:
    if e.get("entity_id","").startswith(("notify.","camera.")):print("NOTIFY_CAMERA_ENTITY",e.get("entity_id"),"disabled",e.get("disabled_by"),flush=True)
  else:
   print("ENABLED_MQTT_CONFIG_COUNT",len([e for e in data if e.get("domain")=="mqtt" and e.get("disabled_by") is None]),flush=True)
 except Exception as e:print("REGISTRY_ERR",name,type(e).__name__,flush=True)
print("CORE_VERSION",Path("/config/.HA_VERSION").read_text().strip() if (P/".HA_VERSION").exists() else "unknown",flush=True)
print("HA_PRIMARY_NOTIFY_PREFLIGHT_COMPLETE",flush=True)
'''
enc="exec(__import__('base64').b64decode("+repr(base64.b64encode(SRC.encode()).decode())+"))"
def ssh(argv,timeout=95):
 p=subprocess.run(["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","nodea",shlex.join(argv)],capture_output=True,text=True,timeout=timeout)
 if p.returncode:raise RuntimeError(p.stderr[-300:])
 return json.loads(p.stdout)
d=ssh(["qm","guest","exec","902","--","docker","exec","homeassistant","python3","-c",enc])
pid=d.get("pid")
for i in range(90):
 if d.get("exited"):break
 if pid is None:raise RuntimeError("NO_GUEST_PID")
 time.sleep(1)
 d=ssh(["qm","guest","exec-status","902",str(pid)],timeout=30)
print("GUEST_EXIT",d.get("exitcode"),flush=True)
print((d.get("out-data") or "")[:9000],flush=True)
print("GUEST_ERR",(d.get("err-data") or "")[-250:],flush=True)
