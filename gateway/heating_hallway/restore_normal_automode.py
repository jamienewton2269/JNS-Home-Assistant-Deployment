#!/usr/bin/env python3
"""Restore explicitly requested automatic 10am heating operation.

One-time action: releases the old global automatic-override flag once
the validated heating schedule and Home Assistant are running. Keeps
manual target hold and all away, fireplace, and safety protections intact.
"""
import base64,json,shlex,subprocess,sys
nodeb=["ssh","-T","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes",
       "-o","HostKeyAlias=nodeb.home.arpa","root@10.10.110.12"]
p="/mnt/data/supervisor/homeassistant/packages/jns_heating_predictive_schedule.yaml"
r=subprocess.run(nodeb+[shlex.join(["qm","guest","exec","905","--","/usr/bin/sha256sum",p])],
                 capture_output=True,text=True,timeout=25)
if r.returncode:raise RuntimeError("Unable to verify active heating package")
obj=json.loads(r.stdout)
if obj.get("exitcode")!=0 or not obj.get("exited"):
    raise RuntimeError("Package integrity query was incomplete")
if not obj.get("out-data","").startswith("3705b3e691d52fd08f"):
    raise RuntimeError("Validated schedule not installed; override unchanged")
remote=r'''
import json,time,urllib.request,urllib.error
key=open("/etc/jns/credentials/ha-general.token").read().strip()
base="http://ha-general.home.arpa/api"
def api(path,data=None):
    hdr={"Authorization":"Bearer "+key}
    if data is not None:hdr["Content-Type"]="application/json"
    req=urllib.request.Request(base+path,headers=hdr,
                               data=json.dumps(data).encode() if data is not None else None)
    with urllib.request.urlopen(req,timeout=12) as response:return json.load(response)
for attempt in range(50):
    try:
        automation=api("/states/automation.jns_heating_predictive_home_10am_and_learned_bedtime_setback")
        override=api("/states/input_boolean.jns_heating_automatic_override")
        manual=api("/states/input_boolean.jns_heating_manual_setpoint_hold")
        break
    except (urllib.error.URLError,TimeoutError):
        time.sleep(3)
else:raise RuntimeError("HA-General unavailable; override unchanged")
if automation["state"]!="on":
    raise RuntimeError("Predictive automation disabled; override unchanged")
if override["state"]=="on":
    api("/services/input_boolean/turn_off",{"entity_id":"input_boolean.jns_heating_automatic_override"})
    updated=api("/states/input_boolean.jns_heating_automatic_override")
    if updated["state"]!="off":raise RuntimeError("Override not verified off")
    print("AUTOMATIC_OVERRIDE_RESET: on -> off")
else:
    print("AUTOMATIC_OVERRIDE_ALREADY_OFF")
print("MANUAL_SETPOINT_HOLD_PRESERVED:",manual["state"])
print("PREDICTIVE_AUTOMATION:",automation["state"])
print("RESTORE_NORMAL_AUTO_MODE_SUCCESS")
'''
command="python3 -c "+shlex.quote("exec(__import__('base64').b64decode('"+base64.b64encode(remote.encode()).decode()+"'))")
runner=subprocess.run(["ssh","-T","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes",
                       "root@10.10.110.13",command],
                      capture_output=True,text=True,timeout=200)
if runner.returncode:
    raise RuntimeError("Protected HA API operation failed: "+runner.stderr[:250])
print(runner.stdout[-800:])
