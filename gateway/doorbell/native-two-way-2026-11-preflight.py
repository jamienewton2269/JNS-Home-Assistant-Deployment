#!/usr/bin/env python3
"""JNS 2026.11 native intercom readiness check. Absolutely read-only.

Run on the Node C trusted GitHub runner. Does not upgrade, snapshot, back up,
restart, reload, install go2rtc, change VM config, or contact public endpoints.
"""
import base64
import datetime as dt
import json
import shlex
import subprocess
import time

CORESRC = r'''
from pathlib import Path
import json,re,platform
p=Path("/config")
def read(reg,key):
 try: return json.loads((p/".storage"/reg).read_text())["data"].get(key,[])
 except Exception:return []
entities=read("core.entity_registry","entities")
entries=read("core.config_entries","entries")
devices=read("core.device_registry","devices")
ver=(p/".HA_VERSION")
print("CORE_VERSION",ver.read_text().strip() if ver.is_file() else "unknown",flush=True)
print("PYTHON_VERSION",platform.python_version(),flush=True)
print("ENABLED_CAMERA_INTEGRATIONS",json.dumps([
 {"domain":e.get("domain"),"title":e.get("title"),"disabled":bool(e.get("disabled_by"))}
 for e in entries
 if e.get("domain") in ("onvif","generic","reolink","tapo","go2rtc","webrtc","stream","mobile_app","mqtt")
])[:12000],flush=True)
print("CAMERA_ENTITIES",json.dumps([
 {"id":e.get("entity_id"),"platform":e.get("platform"),"disabled":bool(e.get("disabled_by"))}
 for e in entities if e.get("entity_id","").startswith("camera.")
])[:12000],flush=True)
print("CAMERA_HARDWARE",json.dumps([
 {"name":d.get("name_by_user") or d.get("name"),
  "manufacturer":d.get("manufacturer"),"model":d.get("model")}
 for d in devices
 if re.search("camera|tapo|reolink|doorbell|c210",str(d.get("name_by_user"))+" "+str(d.get("name"))+" "+str(d.get("model"))+" "+str(d.get("manufacturer")),re.I)
])[:12000],flush=True)
print("WEbrtc_LABS_AVAILABLE","requires Core 2026.11 and entity capability; cannot infer from registry",flush=True)
for name in ("configuration.yaml","automations.yaml"):
 f=p/name
 if f.exists():
  import hashlib
  print("CONFIG_FINGERPRINT",name,f.stat().st_size,hashlib.sha256(f.read_bytes()).hexdigest(),flush=True)
print("CORE_PREFLIGHT_COMPLETE",flush=True)
'''

def ssh(host,command,timeout=30):
    args=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes",host,shlex.join(command)]
    p=subprocess.run(args,text=True,capture_output=True,timeout=timeout)
    if p.returncode:
        raise RuntimeError("SSH_FAILED "+host+" rc="+str(p.returncode)+" "+p.stderr[-180:])
    return p.stdout

def guest(host,vm,command,limit=90):
    d=json.loads(ssh(host,["qm","guest","exec",str(vm),"--",*command],timeout=limit+25))
    pid=d.get("pid");started=time.monotonic()
    while not d.get("exited"):
        if not pid or time.monotonic()-started>limit:raise TimeoutError("QGA_NO_RESULT_OR_TIMEOUT")
        time.sleep(1)
        d=json.loads(ssh(host,["qm","guest","exec-status",str(vm),str(pid)],timeout=25))
    return d.get("exitcode",-1),d.get("out-data",""),d.get("err-data","")

def run(title,host,vm,cmd,limit=90,maxout=5500):
    print("CHECK",title,flush=True)
    try:
        rc,out,err=guest(host,vm,cmd,limit=limit)
        print("RC",rc,flush=True)
        if out:print("OUT",out[:maxout],flush=True)
        if err:print("ERR",err[-350:],flush=True)
    except Exception as e:
        print("UNAVAILABLE",type(e).__name__,str(e)[:200],flush=True)

core="exec(__import__('base64').b64decode("+repr(base64.b64encode(CORESRC.encode()).decode())+"))"
print("JNS_NATIVE_INTERCOM_2026_11_READONLY_BEGIN",dt.datetime.now(dt.timezone.utc).isoformat(),flush=True)
for name,host,vm in (("HA_GENERAL","nodeb","905"),("HA_PRIMARY","nodea","902")):
    print("===== NODE",name,host,vm,"=====",flush=True)
    try:
        output=ssh(host,["qm","config",vm],timeout=18)
        for line in output.splitlines():
            if line.startswith(("memory:","balloon:","cores:","sockets:","onboot:","agent:","scsi0:","virtio0:","ide2:","name:","bios:")):
                # No secure config/credentials, and do not print disk keys.
                print("VM_RESOURCE",line[:180],flush=True)
    except Exception as e: print("VM_RESOURCE_ERROR",str(e)[:120],flush=True)
    run("CORE",host,vm,["ha","core","info"],limit=30,maxout=2700)
    run("OPERATING_SYSTEM",host,vm,["ha","os","info"],limit=30,maxout=2000)
    run("SUPERVISOR",host,vm,["ha","supervisor","info"],limit=30,maxout=2000)
    run("BACKUP_INVENTORY",host,vm,["ha","backups","list"],limit=30,maxout=4000)
    run("CONFIG_AND_CAMERA",host,vm,["docker","exec","homeassistant","python3","-c",core],limit=35,maxout=18000)
    run("DISK_SPACE",host,vm,["df","-h","/mnt/data","/"],limit=20,maxout=1200)
    if name=="HA_GENERAL":
        # Only checks resolution and RTSP port; never fetches credentials/stream.
        run("C210_DNS",host,vm,["getent","ahosts","c210.home.arpa"],limit=15,maxout=1500)
print("UPGRADE_GATES_REQUIRED: stable 2026.11 release, verified restorable local backup, storage headroom, guest CPU/RAM headroom, camera identity, HTTPS, supported WebRTC audio backchannel, explicit approval",flush=True)
print("NO_UPGRADE_NO_RESTART_NO_CAMERA_CHANGES",flush=True)
