#!/usr/bin/env python3
"""Activate already-validated Adaptive Intelligence v0.3.5 on HA-General."""
import json,shlex,subprocess,time
HOST=["ssh","-T","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes",
      "-o","HostKeyAlias=nodeb.home.arpa","-o","ConnectTimeout=8",
      "root@10.10.110.12"]
PATH="/mnt/data/supervisor/homeassistant/custom_components/adaptive_intelligence/manifest.json"
STATUS="/tmp/jns_adaptive_v035_restart.exit"
LOG="/tmp/jns_adaptive_v035_restart.log"

def guest(*args):
    p=subprocess.run(HOST+[shlex.join(["qm","guest","exec","905","--",*args])],
                     capture_output=True,text=True,timeout=35)
    if p.returncode:raise RuntimeError("Node B transport unavailable")
    j=json.loads(p.stdout)
    if not j.get("exited") or j.get("exitcode") != 0:
        raise RuntimeError("Unexpected guest-agent result")
    return j.get("out-data","")

def sh(command):
    return guest("/bin/sh","-c",command)

if '"version": "0.3.5"' not in guest("/bin/cat",PATH):
    raise RuntimeError("Validated version 0.3.5 is not installed")
print("V035_MANIFEST_VERIFIED",flush=True)
sh("rm -f "+shlex.quote(STATUS)+" "+shlex.quote(LOG)+
   "; (ha core restart > "+shlex.quote(LOG)+" 2>&1; echo $? > "+
   shlex.quote(STATUS)+") </dev/null >/dev/null 2>&1 &")
print("SINGLE_CORE_RESTART_REQUESTED",flush=True)
result="PENDING"
for _ in range(170):
    result=sh("test -f "+shlex.quote(STATUS)+" && cat "+shlex.quote(STATUS)+" || echo PENDING").strip()
    if result!="PENDING":break
    time.sleep(3)
if result != "0":
    raise RuntimeError("Core restart did not report successful completion: "+str(result))
print("CORE_RESTART_REPORTED_SUCCESS",flush=True)
print("V035_ACTIVATION_COMPLETE",flush=True)
