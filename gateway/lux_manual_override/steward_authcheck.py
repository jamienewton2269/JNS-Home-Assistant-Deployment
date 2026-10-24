#!/usr/bin/env python3
"""Read-only local authenticated Steward API health probe on HA-General VM905.
Credential never leaves the HA Core container.
"""
import json,sys,time
sys.path.insert(0,'gateway/arrival_lighting')
from readiness_probe import ssh_host
r=json.loads(ssh_host("nodeb",[
  "qm","guest","exec","905","--","docker","exec","homeassistant","python3",
  "/config/.jns-steward/ha_reload_capability.py","probe"
]))
pid=r.get("pid")
for _ in range(40):
  if r.get("exited"):break
  if not isinstance(pid,int):raise RuntimeError("QGA missing PID")
  time.sleep(1)
  r=json.loads(ssh_host("nodeb",["qm","guest","exec-status","905",str(pid)]))
out=r.get("out-data") or ""
if not r.get("exited"):raise RuntimeError("QGA operation did not finish")
if r.get("exitcode")!=0:
  print("JNS_STEWARD_AUTHCHECK_BLOCKED "+(r.get("err-data") or "")[-250:],flush=True)
  raise SystemExit(2)
if "JNS_STEWARD_HA_API_PROBE_OK" not in out:raise SystemExit("No authorised health attestation")
print("JNS_STEWARD_AUTHCHECK_OK_LOCAL_ONLY",flush=True)
