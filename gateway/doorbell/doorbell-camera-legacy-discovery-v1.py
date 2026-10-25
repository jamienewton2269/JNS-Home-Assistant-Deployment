#!/usr/bin/env python3
"""Read-only JNS camera registry discovery on legacy HA900 and HA-Security VM906.

Runs on trusted Node C GitHub Actions runner. No streams opened, credentials
read, camera actions, Core reloads, restarts or guest configuration changes.
"""
import base64
import json
import shlex
import subprocess
import time

CORE = r'''
from pathlib import Path
import json
P=Path("/config/.storage")
def entries(name, key):
    try:
        root=json.loads((P/name).read_text())
        return root.get("data",{}).get(key,[])
    except Exception as exc:
        print("REGISTRY_UNAVAILABLE",name,type(exc).__name__,flush=True)
        return []
entities=entries("core.entity_registry","entities")
devices=entries("core.device_registry","devices")
integrations=entries("core.config_entries","entries")
devmap={d.get("id"):d for d in devices}
platforms={"onvif","tapo","reolink","generic","camera","ffmpeg","go2rtc","webrtc","nest","eufy_security","ring","frigate","unifi","blink","amcrest","hikvision","synology_dsm","remote_homeassistant"}
for c in integrations:
    if c.get("domain") in platforms:
        print("CAMERA_INTEGRATION",json.dumps({"domain":c.get("domain"),"title":c.get("title"),"disabled":bool(c.get("disabled_by"))}),flush=True)
cameras=[e for e in entities if str(e.get("entity_id","")).startswith("camera.")]
print("CAMERA_ENTITY_COUNT",len(cameras),flush=True)
for e in cameras[:90]:
    d=devmap.get(e.get("device_id"),{})
    print("CAMERA_ENTITY",json.dumps({
        "entity":e.get("entity_id"),
        "original_name":e.get("original_name"),
        "name":e.get("name"),
        "platform":e.get("platform"),
        "disabled":bool(e.get("disabled_by")),
        "device_name":d.get("name_by_user") or d.get("name"),
        "manufacturer":d.get("manufacturer"),
        "model":d.get("model"),
    },default=str)[:800],flush=True)
print("CAMERA_REGISTRY_READONLY_COMPLETE",flush=True)
'''
PAYLOAD="exec(__import__('base64').b64decode("+repr(base64.b64encode(CORE.encode()).decode())+"))"

def exec_host(host, args, timeout):
    if host=="nodec":
        command=args
    else:
        command=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes",
                 host,shlex.join(args)]
    result=subprocess.run(command,capture_output=True,text=True,timeout=timeout)
    if result.returncode:
        raise RuntimeError("HOST_EXEC_FAILED "+str(result.returncode)+" "+result.stderr[-140:])
    return json.loads(result.stdout)

def guest(host, vm, cmd, deadline=65):
    data=exec_host(host,["qm","guest","exec",str(vm),"--",*cmd],40)
    started=time.monotonic()
    while not data.get("exited"):
        pid=data.get("pid")
        if not pid or time.monotonic()-started>=deadline:
            raise TimeoutError("QGA_TIMEOUT_OR_PID_MISSING")
        time.sleep(1)
        data=exec_host(host,["qm","guest","exec-status",str(vm),str(pid)],25)
    return data.get("exitcode"),data.get("out-data") or "",data.get("err-data") or ""

print("JNS_LEGACY_FRONTDOOR_CAMERA_DISCOVERY_READONLY",flush=True)
for name,host,vm in [
    ("HA_LEGACY_NODE_A","nodea",900),
    ("HA_SECURITY_NODE_C","nodec",906),
]:
    print("=== GUEST",name,host,vm,"===",flush=True)
    try:
        rc,out,err=guest(host,vm,["docker","exec","homeassistant","python3","-c",PAYLOAD])
        print("RESULT",name,"rc",rc,flush=True)
        print(out[:23000],flush=True)
        if rc!=0:
            print("ERROR",name,err[-350:],flush=True)
    except Exception as exc:
        print("AUDIT_INCONCLUSIVE",name,type(exc).__name__,str(exc)[:220],flush=True)
print("NO_CAMERA_OR_CORE_CHANGES",flush=True)
