#!/usr/bin/env python3
"""Read-only check that the live heating schedule is a byte-exact JNS release.
Returns only hashes and expected automation identities, no HA credentials or
temperatures; all VM905 changes are forbidden in this probe.
"""
import base64,hashlib,json,pathlib,sys,time
sys.path.insert(0,"gateway/arrival_lighting")
from readiness_probe import ssh_host
SOURCE=pathlib.Path("gateway/heating_presence/jns_predictive_schedule.yaml")
INNER=r'''
import pathlib,hashlib,json,yaml
p=pathlib.Path("/config/packages/jns_heating_predictive_schedule.yaml")
assert p.is_file() and not p.is_symlink(),"Heating package unavailable"
b=p.read_bytes()
cfg=yaml.safe_load(b)
automations=cfg.get("automation",[])
expected=["jns_heating_learn_bedtime_v1","jns_heating_alarm_predictive_target_v1"]
# Do not infer an exclusive thermostat writer merely from the known package:
# report other local files referencing the exact physical climate target.
root=pathlib.Path("/config")
other_writers=[]
for folder in (root/"packages",root/"scripts",root):
 if not folder.is_dir(): continue
 for candidate in folder.glob("*.yaml"):
  if candidate==p:continue
  try:
   text=candidate.read_text(errors="replace")
   if "climate.thermostat_thermostat" in text and (
      "climate.set_temperature" in text or "climate.set_hvac_mode" in text):
    name=str(candidate.relative_to(root))
    if name not in other_writers:other_writers.append(name)
  except OSError:pass
print("JNS_MANUAL_BOOST_PREFLIGHT "+json.dumps({
 "live_sha256":hashlib.sha256(b).hexdigest(),
 "automation_ids_match": [a.get("id") for a in automations]==expected,
 "manual_override_helper_declared":"jns_heating_automatic_override" in cfg.get("input_boolean",{}),
 "has_five_minute_trigger":any(x.get("trigger")=="time_pattern" and x.get("minutes")=="/5"
  for x in automations[1].get("triggers",[])),
 "existing_manual_high_setpoint_exemption":"JNS_MANUAL_HIGH_HEAT_PRESERVED_V1" in b.decode(),
 "existing_heat_script_only":len(automations)==2,
 "other_referencing_files":sorted(other_writers)[:30],
 "other_referencing_count":len(other_writers),
 "scope":"VM905_READ_ONLY"
},sort_keys=True))
'''
def main():
 if "running" not in ssh_host("nodeb",["qm","status","905"]):raise RuntimeError("VM905 stopped")
 s=base64.b64encode(INNER.encode()).decode()
 r=json.loads(ssh_host("nodeb",["qm","guest","exec","905","--","docker","exec","homeassistant","python3","-c","exec(__import__('base64').b64decode('"+s+"'))"]))
 deadline=time.monotonic()+75
 while not r.get("exited"):
  if time.monotonic()>deadline or not isinstance(r.get("pid"),int):raise RuntimeError("preflight unresolved")
  time.sleep(2)
  r=json.loads(ssh_host("nodeb",["qm","guest","exec-status","905",str(r["pid"])]))
 if r.get("exitcode")!=0:raise RuntimeError("preflight could not inspect existing schedule")
 output=r.get("out-data") or ""
 if not output.startswith("JNS_MANUAL_BOOST_PREFLIGHT "):raise RuntimeError("preflight output invalid")
 result=json.loads(output.split(" ",1)[1])
 expected=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
 result["matches_main_release"]=result["live_sha256"]==expected
 print("JNS_MANUAL_BOOST_PREFLIGHT "+json.dumps(result,sort_keys=True))
if __name__=="__main__":main()
