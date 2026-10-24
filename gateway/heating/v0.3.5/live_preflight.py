#!/usr/bin/env python3
"""JNS GitHub runner to VM905 QGA: *preflight only*.

This is not an installer and deliberately does not expose stage/commit or
rollback remotely. Production activation requires a separate approved
root-owned JNS gateway handler and planned HA restart.
"""
import base64
import json
from pathlib import Path
import sys
import time

sys.path.insert(0,"gateway/arrival_lighting")
from readiness_probe import ssh_host

ROOT=Path("gateway/heating/v0.3.5")
TRANSACTION=(ROOT/"transaction.py").read_bytes()
CANDIDATE=(ROOT/"thermal.py").read_bytes()
if not TRANSACTION or not CANDIDATE:
    raise RuntimeError("candidate package missing")
payload=(
    "import base64,sys\n"
    "CANDIDATE_BYTES=base64.b64decode("+repr(base64.b64encode(CANDIDATE).decode())+")\n"
    "sys.argv=['transaction.py','preflight','--root','/config','--candidate','-']\n"
    "exec(compile(base64.b64decode("+repr(base64.b64encode(TRANSACTION).decode())+
    "),'<jns-heating-preflight>','exec'))\n"
)
encoded=base64.b64encode(payload.encode()).decode()
expression="exec(__import__('base64').b64decode('"+encoded+"'))"
r=json.loads(ssh_host("nodeb",["qm","guest","exec","905","--",
  "docker","exec","homeassistant","python3","-c",expression]))
deadline=time.monotonic()+95
while not r.get("exited"):
    if not isinstance(r.get("pid"),int) or time.monotonic()>deadline:
        raise RuntimeError("VM905 preflight did not exit; no changes attempted")
    time.sleep(1)
    r=json.loads(ssh_host("nodeb",["qm","guest","exec-status","905",str(r["pid"])]))
message=(r.get("out-data") or "").strip()
if r.get("exitcode")!=0 or not message.startswith("JNS_HEATING_GUARDED "):
    print("JNS_HEATING_PREFLIGHT_BLOCKED",
          message[-400:] if message.startswith("JNS_HEATING_BLOCKED") else
          "QGA error or unexpected output",flush=True)
    sys.exit(2)
report=json.loads(message.partition(" ")[2])
if report.get("state")!="preflight_passed" or not report.get("configuration_unchanged"):
    raise RuntimeError("VM905 failed heating source guard")
print("JNS_HEATING_V035_PREFLIGHT",json.dumps(report,sort_keys=True),flush=True)
