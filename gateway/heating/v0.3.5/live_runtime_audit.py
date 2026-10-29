#!/usr/bin/env python3
"""Read-only VM905 heating runtime entity attestation via current Steward token.

Token stays inside Home Assistant. No HA actions or setpoints are changed.
"""
import base64,json
from pathlib import Path
import sys,time
sys.path.insert(0,"gateway/arrival_lighting")
from readiness_probe import ssh_host
code=Path("gateway/heating/v0.3.5/runtime_api_check.py").read_bytes()
expr="exec(compile(__import__('base64').b64decode("+repr(base64.b64encode(code).decode())+"),'<jns-heating-runtime-check>','exec'))"
r=json.loads(ssh_host("nodeb",["qm","guest","exec","905","--",
  "docker","exec","homeassistant","python3","-c",expr]))
deadline=time.monotonic()+75
while not r.get("exited"):
    if not isinstance(r.get("pid"),int) or time.monotonic()>deadline:
        raise RuntimeError("runtime query did not complete; no writes attempted")
    time.sleep(1)
    r=json.loads(ssh_host("nodeb",["qm","guest","exec-status","905",str(r["pid"])]))
output=(r.get("out-data") or "").strip()
if r.get("exitcode")!=0 or not output.startswith("JNS_HEATING_RUNTIME "):
    print("JNS_HEATING_RUNTIME_AUDIT_BLOCKED",
          (r.get("err-data") or "unavailable")[-150:],flush=True)
    sys.exit(2)
report=json.loads(output.partition(" ")[2])
if not report.get("ready") or not all(report.get(x) for x in
          ("climate_ok","indoor_ok","heating_call_ok","learner_exists")):
    raise RuntimeError("Essential heating runtime entities not verified")
print("JNS_HEATING_RUNTIME_VERIFIED",json.dumps(report,sort_keys=True),flush=True)
