#!/usr/bin/env python3
"""Read-only post-stage integrity verification on VM905 via JNS Node C runner."""
import base64
import json
from pathlib import Path
import re
import sys
import time

sys.path.insert(0,"gateway/arrival_lighting")
from readiness_probe import ssh_host

pairs={}
for line in Path("gateway/heating/v0.3.5/verify.request").read_text().splitlines():
    if "=" in line:
        key,value=line.split("=",1)
        pairs[key.strip()]=value.strip()
stage_id=pairs.get("stage_id","")
if not re.fullmatch(r"v035-\d{8}T\d{6}Z-[0-9a-f]{8}",stage_id):
    raise RuntimeError("unrecognised stage identifier")
code=Path("gateway/heating/v0.3.5/transaction.py").read_bytes()
inner=(
    "import base64,sys\n"
    "sys.argv=['transaction.py','verify','--root','/config','--stage-id',"+
     repr(stage_id)+"]\n"
    "exec(compile(base64.b64decode("+repr(base64.b64encode(code).decode())+
    "),'<jns-heating-stage-verifier>','exec'))\n"
)
command="exec(__import__('base64').b64decode('"+base64.b64encode(inner.encode()).decode()+"'))"
result=json.loads(ssh_host("nodeb",["qm","guest","exec","905","--",
  "docker","exec","homeassistant","python3","-c",command]))
deadline=time.monotonic()+90
while not result.get("exited"):
    if not isinstance(result.get("pid"),int) or time.monotonic()>deadline:
        raise RuntimeError("guest verify not finished; no writes attempted")
    time.sleep(1)
    result=json.loads(ssh_host("nodeb",["qm","guest","exec-status","905",str(result["pid"])]))
message=(result.get("out-data") or "").strip()
if result.get("exitcode") or not message.startswith("JNS_HEATING_GUARDED "):
    print("JNS_HEATING_STAGE_VERIFY_BLOCKED",
      message[-220:] if message.startswith("JNS_HEATING_BLOCKED ") else
      "unverified QGA result",flush=True)
    raise SystemExit(2)
status=json.loads(message.partition(" ")[2])
if not (status.get("state")=="staged" and status.get("backups_integrity_verified")
        and status.get("runtime_reload") is False):
    raise RuntimeError("verification incomplete")
print("JNS_HEATING_PRIVATE_STAGE_VERIFIED",
      json.dumps({"stage_id":stage_id,**status},sort_keys=True),flush=True)
