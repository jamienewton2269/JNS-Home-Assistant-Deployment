#!/usr/bin/env python3
"""Read-only SSH add-on Supervisor API check of four fixed VM905 heating states."""
import json,sys,time
from pathlib import Path
sys.path.insert(0,"gateway/arrival_lighting")
from readiness_probe import ssh_host

CODE=Path("gateway/heating/v0.3.5/runtime_supervisor_check.sh").read_text()
r=json.loads(ssh_host("nodeb",["qm","guest","exec","905","--",
    "docker","exec","app_core_ssh","sh","-c",CODE]))
deadline=time.monotonic()+95
while not r.get("exited"):
    if not isinstance(r.get("pid"),int) or time.monotonic()>deadline:
        raise RuntimeError("SSH add-on read-only runtime check did not finish")
    time.sleep(1)
    r=json.loads(ssh_host("nodeb",["qm","guest","exec-status","905",str(r["pid"])]))
text=(r.get("out-data") or "").strip()
if r.get("exitcode")!=0 or text!="JNS_HEATING_RUNTIME_AUTHENTICATED_READY":
    print("JNS_HEATING_SUPERVISOR_AUDIT_BLOCKED",
          text[-100:] if text.startswith("JNS_HEATING_") else "unverified",flush=True)
    sys.exit(2)
print("JNS_HEATING_SUPERVISOR_RUNTIME_VERIFIED",
      "essential_entities=4 local_auth_only=true unchanged=true",flush=True)
