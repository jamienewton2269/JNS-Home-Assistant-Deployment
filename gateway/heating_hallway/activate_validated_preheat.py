#!/usr/bin/env python3
"""Activate already-validated HA-General heating package, check Core health."""
import json, shlex, subprocess, time, hashlib, sys
HOST=["ssh","-T","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes",
      "-o","HostKeyAlias=nodeb.home.arpa","-o","ConnectTimeout=7","root@10.10.110.12"]
P="/mnt/data/supervisor/homeassistant/packages/jns_heating_predictive_schedule.yaml"
EXPECTED="3705b3e691d52fd08f"
def guest(*args):
    q=["qm","guest","exec","905","--"]+list(args)
    p=subprocess.run(HOST+[shlex.join(q)],text=True,capture_output=True,timeout=35)
    if p.returncode: raise RuntimeError("Node B guest command unavailable")
    j=json.loads(p.stdout)
    if j.get("exitcode",0)!=0:raise RuntimeError("Guest command exited with error")
    if not j.get("exited"):raise RuntimeError("Unexpected nonblocking guest status")
    return j.get("out-data","")
def shell(c):
    return guest("/bin/sh","-c",c)
actual=guest("/usr/bin/sha256sum",P).split()[0]
if not actual.startswith(EXPECTED):
    raise RuntimeError("Deployed schedule checksum does not match validated patch")
print("VALIDATED_HEATING_PACKAGE_PRESENT",actual[:18],flush=True)
status="/tmp/jns_preheat_restart_20261117.exit"
log="/tmp/jns_preheat_restart_20261117.log"
shell("rm -f "+shlex.quote(status)+" "+shlex.quote(log)+
      "; (ha core restart > "+shlex.quote(log)+
      " 2>&1; echo $? > "+shlex.quote(status)+") </dev/null >/dev/null 2>&1 &")
print("CORE_RESTART_REQUESTED",flush=True)
result=None
for attempt in range(140):
    state=shell("test -f "+shlex.quote(status)+" && cat "+shlex.quote(status)+" || echo WAIT").strip()
    if state!="WAIT":
        result=state
        break
    time.sleep(2)
if result!="0":
    raise RuntimeError("Core restart did not report success: "+str(result))
print("CORE_RESTART_REPORTED_SUCCESS",flush=True)
for attempt in range(45):
    try:
        status_text=shell("ha core info").lower()
    except Exception:
        time.sleep(2);continue
    if "state: running" in status_text or '"state": "running"' in status_text:
        print("CORE_RUNNING_CONFIRMED",flush=True)
        break
    time.sleep(2)
else:
    print("CORE_INFO_NOT_YET_CONFIRMED",flush=True)
print("HEATING_ACTIVATION_COMPLETE",flush=True)
