#!/usr/bin/env python3
"""Read-only audit of forecast consumers on VM905; print file paths/count only."""
import base64,json,sys,time
sys.path.insert(0,"gateway/arrival_lighting")
from readiness_probe import ssh_host
INNER=r'''
import json,pathlib,re
root=pathlib.Path("/config")
ids=("sensor.lyric_home_heating_projected_temperature_in_60_minutes",
     "sensor.lyric_home_heating_thermal_learning",
     "sensor.0xa4c1382471d2ed23_temperature")
out={}
paths=[p for p in root.glob("*.yaml") if p.is_file()]
for folder in ("packages","scripts","automations","dashboards"):
 f=root/folder
 if f.is_dir():
  paths.extend(p for p in f.rglob("*.yaml") if p.is_file())
for p in paths[:1200]:
 try:
  if p.stat().st_size>1_000_000:continue
  data=p.read_text()
  ids_found=[x for x in ids if x in data]
  if ids_found:
   out[str(p.relative_to(root))]=ids_found
 except (OSError,UnicodeError):pass
print(json.dumps({"references":out,"scanned_yaml_count":len(paths)},sort_keys=True))
'''
cmd="exec(__import__('base64').b64decode('"+base64.b64encode(INNER.encode()).decode()+"'))"
r=json.loads(ssh_host("nodeb",["qm","guest","exec","905","--","docker","exec","homeassistant","python3","-c",cmd]))
deadline=time.monotonic()+90
while not r.get("exited"):
 if not isinstance(r.get("pid"),int) or time.monotonic()>deadline:raise RuntimeError("forecast consumer audit timed out")
 time.sleep(1);r=json.loads(ssh_host("nodeb",["qm","guest","exec-status","905",str(r["pid"])]))
if r.get("exitcode")!=0:raise RuntimeError("forecast consumer audit failed")
print("JNS_HEATING_FORECAST_CONSUMERS",r.get("out-data") or "{}")
