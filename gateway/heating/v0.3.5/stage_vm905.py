#!/usr/bin/env python3
"""Privately stage v0.3.5 files on VM905 without altering the active integration.

Executed only by an explicitly triggered, self-hosted Node C workflow after
CI and live read-only preflight. No HA reload/restart or code activation.
"""
import base64
import json
from pathlib import Path
import sys
import time

sys.path.insert(0,"gateway/arrival_lighting")
from readiness_probe import ssh_host

FOLDER=Path("gateway/heating/v0.3.5")
script=(FOLDER/"transaction.py").read_bytes()
candidate=(FOLDER/"thermal.py").read_bytes()
inner=(
    "import base64,sys\n"
    "CANDIDATE_BYTES=base64.b64decode("+repr(base64.b64encode(candidate).decode())+")\n"
    "sys.argv=['transaction.py','stage','--root','/config','--candidate','-']\n"
    "exec(compile(base64.b64decode("+repr(base64.b64encode(script).decode())+
    "),'<jns-heating-private-stage>','exec'))\n"
)
command="exec(__import__('base64').b64decode('"+base64.b64encode(inner.encode()).decode()+"'))"
result=json.loads(ssh_host("nodeb",["qm","guest","exec","905","--",
        "docker","exec","homeassistant","python3","-c",command]))
end=time.monotonic()+95
while not result.get("exited"):
    if not isinstance(result.get("pid"),int) or time.monotonic()>end:
        raise RuntimeError("VM905 stage did not exit; inspect privately before repeating")
    time.sleep(1)
    result=json.loads(ssh_host("nodeb",["qm","guest","exec-status","905",str(result["pid"])]))
output=(result.get("out-data") or "").strip()
if result.get("exitcode")!=0 or not output.startswith("JNS_HEATING_GUARDED "):
    print("JNS_HEATING_STAGE_BLOCKED",
          output[-250:] if output.startswith("JNS_HEATING_BLOCKED ") else
          "QGA failed or unexpected output",flush=True)
    raise SystemExit(2)
report=json.loads(output.partition(" ")[2])
if report.get("state")!="staged" or not report.get("runtime_untouched"):
    raise RuntimeError("stage result did not prove live files untouched")
print("JNS_HEATING_PRIVATELY_STAGED",json.dumps(report,sort_keys=True),flush=True)
