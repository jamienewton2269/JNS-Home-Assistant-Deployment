#!/usr/bin/env python3
"""Inventory VM900 add-on/container metadata *privately on Node A*.
An evidence manifest is written root-only in /var/lib/jns-solar/ha900.
No VM changes, Docker changes, add-on changes, or user secrets are collected.
Only status/count/checksum are returned in public GitHub Actions logs.
A separate guarded transfer will import into protected Node C Steward.
"""
import base64
import shlex
import subprocess
import sys

REMOTE = r'''
import datetime
import hashlib
import json
import os
import pathlib
import re
import subprocess
import tempfile
import time

if os.geteuid()!=0 or os.uname().nodename.split(".")[0]!="nodea":
    raise SystemExit("BLOCKED wrong_host_or_not_root")
def guest(args):
    p=subprocess.run(["qm","guest","exec","900","--",*args],
                     capture_output=True,text=True,timeout=38)
    if p.returncode:
        raise RuntimeError("guest_exec_transport")
    try: x=json.loads(p.stdout)
    except ValueError:raise RuntimeError("guest_exec_json")
    for _ in range(12):
        if x.get("exited"):break
        pid=x.get("pid")
        if pid is None:raise RuntimeError("guest_exec_missing_pid")
        time.sleep(0.5)
        p=subprocess.run(["qm","guest","exec-status","900",str(pid)],
                         capture_output=True,text=True,timeout=15)
        if p.returncode:raise RuntimeError("guest_exec_status")
        x=json.loads(p.stdout)
    if not x.get("exited") or x.get("exitcode")!=0:
        raise RuntimeError("guest_exec_exit_or_timeout")
    return x.get("out-data","")
state=subprocess.run(["qm","status","900"],capture_output=True,text=True,timeout=8)
if state.returncode or "running" not in state.stdout:
    raise SystemExit("BLOCKED vm900_not_running")
raw=guest(["docker","ps","-a","--format","{{json .}}"])
containers=[]
for line in raw.splitlines():
    try:
        d=json.loads(line)
    except ValueError:
        raise RuntimeError("unexpected_docker_list_format")
    # Only version/placement/dependency metadata; never env variables, labels,
    # config files, encryption material, entity states or credentials.
    containers.append({
        "name":d.get("Names",""),
        "image":d.get("Image",""),
        "container_id":d.get("ID",""),
        "status":d.get("Status",""),
        "ports":d.get("Ports",""),
        "mounts_summary":d.get("Mounts",""),
    })
ids=[x["container_id"] for x in containers if x["container_id"]]
if not ids or len(containers)>150:
    raise RuntimeError("unexpected_container_inventory_size")
inspection=guest(["docker","inspect","--format",
                  "{{.Id}}|{{json .Mounts}}|{{json .HostConfig.PortBindings}}",
                  *ids])
details=[]
for row in inspection.splitlines():
    p=row.split("|",2)
    if len(p)!=3:raise RuntimeError("inspect_parse_error")
    try:
        details.append({"id":p[0],"mounts":json.loads(p[1]),
                        "port_bindings":json.loads(p[2])})
    except ValueError:raise RuntimeError("inspect_json_error")
if len(details)!=len(containers):
    raise RuntimeError("inspect_count_mismatch")
roles=("audio","dns","esphome","multicast","observer","piper","ssh",
       "supervisor","mqtt","matter","zigbee","go2rtc","influxdb")
for c in containers:
    c["role_candidate"]=next((v for v in roles if v in c["name"].lower()),"unclassified")
manifest={
    "schema":"jns.solar.vm900.services.v1",
    "created_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "source_host":"nodea","vmid":900,
    "purposes":["historical_reference","dependency_review","safe_addon_cleanup"],
    "secrets_exported":False,
    "container_count":len(containers),
    "running_count":sum(c["status"].startswith("Up ") for c in containers),
    "containers":containers,
    "mount_and_port_bindings":details,
    "cleanup_authorised":False,
    "dependency_verification_complete":False,
    "full_restore_backup_verified":False,
}
dest=pathlib.Path("/var/lib/jns-solar/ha900/evidence")
dest.mkdir(parents=True,exist_ok=True,mode=0o700)
os.chmod(dest,0o700)
raw=json.dumps(manifest,sort_keys=True,indent=2).encode()
sha=hashlib.sha256(raw).hexdigest()
name="vm900-services-"+datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")+".json"
fd,tmp=tempfile.mkstemp(prefix=".vm900-services-",dir=str(dest))
try:
    with os.fdopen(fd,"wb") as fh:
        fh.write(raw)
        fh.flush()
        os.fsync(fh.fileno())
    os.chmod(tmp,0o600)
    os.replace(tmp,dest/name)
finally:
    if os.path.exists(tmp):os.unlink(tmp)
# Public stdout: no names, addresses, image refs, mounts or private data.
print("JNS_VM900_PRIVATE_INVENTORY_CAPTURED")
print("CONTAINER_COUNT="+str(len(containers)))
print("RUNNING_COUNT="+str(manifest["running_count"]))
print("HASH_SHA256="+sha)
print("SOURCE_ROOT_ONLY_LOCATION=var/lib/jns-solar/ha900/evidence")
print("CLEARED_FOR_CLEANUP=no")
'''
encoded=base64.b64encode(REMOTE.encode()).decode()
cmd=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes",
     "-o","ConnectTimeout=6","nodea",shlex.join(["python3","-c",
     "exec(__import__('base64').b64decode('"+encoded+"'))"])]
try:r=subprocess.run(cmd,capture_output=True,text=True,timeout=145)
except (OSError,subprocess.TimeoutExpired):
    print("JNS_VM900_INVENTORY_BLOCKED=transport_timeout")
    sys.exit(2)
if r.returncode:
    # Never print raw stdout/stderr; classify errors from safe known markers.
    indicators=("wrong_host_or_not_root","vm900_not_running",
      "guest_exec_transport","guest_exec_json","guest_exec_missing_pid",
      "guest_exec_status","guest_exec_exit_or_timeout",
      "unexpected_docker_list_format","unexpected_container_inventory_size",
      "inspect_parse_error","inspect_json_error","inspect_count_mismatch",
      "SyntaxError","PermissionError","FileNotFoundError","TypeError",
      "NameError","ValueError","RuntimeError","ConnectionError")
    reason=next((a for a in indicators if a in r.stderr or a in r.stdout),"unclassified")
    print("JNS_VM900_INVENTORY_BLOCKED=remote_failure_exit_"+str(r.returncode))
    print("JNS_VM900_FAILURE_CLASS="+reason)
    sys.exit(r.returncode if r.returncode<125 else 3)
if "JNS_VM900_PRIVATE_INVENTORY_CAPTURED" not in r.stdout:
    print("JNS_VM900_INVENTORY_BLOCKED=missing_success_marker")
    sys.exit(4)
for line in r.stdout.splitlines():
    if line.startswith(("JNS_VM900_PRIVATE_INVENTORY_CAPTURED",
                        "CONTAINER_COUNT=","RUNNING_COUNT=",
                        "HASH_SHA256=","SOURCE_ROOT_ONLY_LOCATION=",
                        "CLEARED_FOR_CLEANUP=")):
        print(line)
