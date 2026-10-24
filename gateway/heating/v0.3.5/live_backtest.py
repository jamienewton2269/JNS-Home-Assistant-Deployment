#!/usr/bin/env python3
"""Read-only shadow evaluation of staged v0.3.5 against VM905 saved samples.

Runs from the authorised Node C GitHub runner. No HA component is overwritten,
reloaded, restarted, or installed. Raw samples never leave the HA guest.
"""
import base64
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, "gateway/arrival_lighting")
from readiness_probe import ssh_host

candidate=Path("gateway/heating/v0.3.5/thermal.py").read_bytes()
GUEST=r"""
import base64,hashlib,json,pathlib,sys,types
home=pathlib.Path("/config")
component=home/"custom_components"/"jns_heating_zones"
manifest=json.loads((component/"manifest.json").read_text())
if manifest.get("version")!="0.3.4":
    raise RuntimeError("Unexpected live heating version")
baseline_code=(component/"thermal.py").read_bytes()
if b'Per-zone thermal learner.' not in baseline_code[:140]:
    raise RuntimeError("Unexpected baseline thermal.py header")
def load_module(name,source):
    obj=types.ModuleType(name)
    sys.modules[name]=obj
    exec(compile(source,"<"+name+">","exec"),obj.__dict__)
    return obj
old=load_module("_jns_thermal_v034_shadow",baseline_code)
new=load_module("_jns_thermal_v035_shadow",base64.b64decode(CANDIDATE_B64))
stores=sorted((home/".storage").glob("jns_heating_zone_*"))
if not stores:
    raise RuntimeError("Heating storage not found")
results=[]
for path in stores:
    raw=path.read_bytes()
    saved=json.loads(raw)
    records=saved.get("data",{}).get("samples")
    if not isinstance(records,list):
        raise RuntimeError("Unexpected storage format")
    before=hashlib.sha256(raw).hexdigest()
    v034=old.ZoneLearner(records)
    v035=new.ZoneLearner(records)
    result0=v034.status()
    result1=v035.status()
    if v035.dump()!=records:
        raise RuntimeError("Candidate altered persisted sample representation")
    if before!=hashlib.sha256(path.read_bytes()).hexdigest():
        raise RuntimeError("Stored samples changed during read-only audit")
    def fields(s):
        return {k:s.get(k) for k in
         ("ready","samples","reason","stored_samples","valid_windows",
          "nonzero_delta_windows","heated_windows","unheated_windows",
          "coarse_sensor","indoor_levels","short_5min_adjacent_pairs",
          "loss_per_hour","heat_gain_c_per_hour","drift_c_per_hour")
          if k in s}
    results.append({"samples":len(records),"legacy":fields(result0),
        "candidate":fields(result1),"storage_unchanged":True})
print(json.dumps({"live_version":manifest.get("version"),
 "zone_count":len(results),"zones":results},sort_keys=True))
"""
script=GUEST.replace("CANDIDATE_B64",repr(base64.b64encode(candidate).decode()))
command="exec(__import__('base64').b64decode('"+base64.b64encode(script.encode()).decode()+"'))"
res=json.loads(ssh_host("nodeb",["qm","guest","exec","905","--",
                                   "docker","exec","homeassistant","python3","-c",command]))
limit=time.monotonic()+90
while not res.get("exited"):
    if not isinstance(res.get("pid"),int) or time.monotonic()>limit:
        raise RuntimeError("VM905 QGA did not complete; cannot verify")
    time.sleep(1)
    res=json.loads(ssh_host("nodeb",["qm","guest","exec-status","905",str(res["pid"])]))
if res.get("exitcode") != 0:
    print("HEATING_SHADOW_BACKTEST_BLOCKED",str(res.get("err-data",""))[-450:])
    sys.exit(1)
report=json.loads(res.get("out-data") or "{}")
if not report.get("zones") or not all(x["storage_unchanged"] for x in report["zones"]):
    raise RuntimeError("Incomplete shadow report")
print("JNS_HEATING_SHADOW_BACKTEST",json.dumps(report,sort_keys=True))
