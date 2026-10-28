#!/usr/bin/env python3
"""Stage source Lovelace dashboard definitions privately for selective HA merge.

Node C runner -> authorised Node A/B QGA -> Node B private host directory.
Never writes to /config, copies .storage registries, sends device commands,
restarts Core, or changes HA ownership. No secret/dashboard content in CI logs.
"""
import base64
import json
import os
import shlex
import subprocess
import time

SSH = ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
       "-o", "ConnectTimeout=6"]
EXTRACT = r'''
import base64,json,pathlib,re,sys,zlib
role=sys.argv[1]
root=pathlib.Path("/config/.storage")
index=root/"lovelace_dashboards"
if not index.is_file() or index.is_symlink():raise SystemExit(70)
obj=json.loads(index.read_text())
items=obj.get("data",{}).get("items",[])
if not isinstance(items,list):raise SystemExit(71)
output=[]
for e in items:
 if not isinstance(e,dict):raise SystemExit(72)
 path=e.get("url_path")
 if not isinstance(path,str) or not path or len(path)>200:raise SystemExit(73)
 record={"metadata":e,"url_path":path}
 if role=="source":
  ident=e.get("id")
  if not isinstance(ident,(str,int)) or not re.fullmatch(r"[A-Za-z0-9_-]{1,90}",str(ident)):
   record["backing_file"]="id_not_safe"
  else:
   f=root/("lovelace."+str(ident))
   if f.is_symlink():raise SystemExit(74)
   if f.is_file():
    data=f.read_bytes()
    if len(data)>1200000:raise SystemExit(75)
    record["backing_file"]="captured"
    record["file_basename"]=f.name
    record["file_data_b64"]=base64.b64encode(data).decode()
   else:record["backing_file"]="not_found"
 output.append(record)
payload=json.dumps({"role":role,"items":output},sort_keys=True,separators=(",",":")).encode()
if len(payload)>2600000:raise SystemExit(76)
print("JNS_PRIVATE_DASHBOARD_BLOB="+base64.b64encode(zlib.compress(payload,9)).decode())
'''
STAGE = r'''
import base64,hashlib,json,os,pathlib,shutil,sys,tempfile
if os.geteuid()!=0 or os.uname().nodename.split(".")[0]!="nodeb":raise SystemExit(70)
root=pathlib.Path("/var/lib/jns-solar/consolidation")
dest=root/"ha-dashboards-20261028-v1"
if not root.is_dir() or root.is_symlink() or dest.exists() or dest.is_symlink():
 print("JNS_DASH_PRIVATE_STAGE_BLOCKED=destination_or_root");raise SystemExit(71)
payload=sys.stdin.buffer.read(3500000)
if not payload or len(payload)>3000000:raise SystemExit(72)
obj=json.loads(payload)
if obj.get("target_vm")!=905 or obj.get("source_vms")!=[902,906]:raise SystemExit(73)
rows=obj.get("missing")
if not isinstance(rows,list) or len(rows)>25:raise SystemExit(74)
tmp=pathlib.Path(tempfile.mkdtemp(dir=root,prefix=".ha-dashboard-stage-"))
tmp.chmod(0o700)
def private_write(path,raw):
 if not path.parent.is_dir():path.parent.mkdir(mode=0o700,parents=True)
 with path.open("xb") as f:
  f.write(raw);f.flush();os.fsync(f.fileno())
 path.chmod(0o600)
try:
 manifest={"stage_version":1,"source_vms":[902,906],"target_vm":905,
           "not_imported":True,"no_core_changes":True,"missing_dashboards":[]}
 missing_files=0
 for row in rows:
  vm=row.get("vm")
  e=row.get("record")
  if vm not in (902,906) or not isinstance(e,dict):raise ValueError("invalid_row")
  data=e.get("file_data_b64")
  item={"source_vm":vm,"metadata":e.get("metadata"),
        "backing_file":e.get("backing_file")}
  if data is not None:
   raw=base64.b64decode(data,validate=True)
   if len(raw)>1200000:raise ValueError("oversized")
   slug=hashlib.sha256((str(vm)+":"+str(e.get("url_path"))).encode()).hexdigest()[:20]
   fname="source-"+str(vm)+"/"+slug+".json"
   private_write(tmp/fname,raw)
   item["staged_filename"]=fname
   item["sha256"]=hashlib.sha256(raw).hexdigest()
  else:
   missing_files+=1
  manifest["missing_dashboards"].append(item)
 private_write(tmp/"manifest.json",json.dumps(manifest,sort_keys=True,indent=2).encode()+b"\n")
 os.rename(tmp,dest)
except BaseException:
 shutil.rmtree(tmp,ignore_errors=True)
 print("JNS_DASH_PRIVATE_STAGE_BLOCKED=payload_or_write")
 raise SystemExit(75)
print("JNS_DASH_PRIVATE_STAGE_OK="+json.dumps({
 "source_vm_count":2,"target_vm":905,"missing_dashboard_count":len(rows),
 "missing_backing_file_count":missing_files,"private_host_only":True,
 "target_ha_config_modified":False,"core_restarted":False},sort_keys=True))
'''

def run(args, timeout=50, stdin=None):
    try:
        return subprocess.run(args, input=stdin, capture_output=True,
                              text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return None

def ssh(node, args, timeout=40, stdin=None):
    return run(SSH + [node, shlex.join(args)], timeout, stdin)

def guest(node, vm, role):
    code = base64.b64encode(EXTRACT.encode()).decode()
    command = ["qm", "guest", "exec", str(vm), "--", "docker", "exec",
               "homeassistant", "python3", "-c",
               "exec(__import__('base64').b64decode('" + code + "'))", role]
    res = ssh(node, command, 55)
    if not res or res.returncode:
        return None
    try:
        job = json.loads(res.stdout)
    except ValueError:
        return None
    deadline = time.monotonic() + 80
    while time.monotonic() < deadline:
        if job.get("exited"):
            break
        if not job.get("pid"):
            return None
        time.sleep(.5)
        res = ssh(node, ["qm", "guest", "exec-status", str(vm), str(job["pid"])], 20)
        if not res or res.returncode:
            return None
        try:
            job = json.loads(res.stdout)
        except ValueError:
            return None
    if not job.get("exited") or job.get("exitcode") != 0 or job.get("out-truncated"):
        return None
    rows = [x.split("=", 1)[1] for x in str(job.get("out-data", "")).splitlines()
            if x.startswith("JNS_PRIVATE_DASHBOARD_BLOB=")]
    if len(rows) != 1:
        return None
    try:
        import zlib
        data = zlib.decompress(base64.b64decode(rows[0], validate=True))
        if len(data)>2600000:
            return None
        parsed=json.loads(data)
    except (ValueError, TypeError, OverflowError, zlib.error):
        return None
    return parsed if parsed.get("role") == role else None

def main():
    if os.uname().nodename.split(".")[0] != "nodec":
        print("JNS_DASH_PRIVATE_STAGE_BLOCKED=wrong_runner")
        return 1
    for node,vm in (("nodea",902),("nodea",906),("nodeb",905)):
        res=ssh(node,["qm","status",str(vm)],22)
        if not res or res.returncode or res.stdout.strip()!="status: running":
            print("JNS_DASH_PRIVATE_STAGE_BLOCKED=source_or_target_offline")
            return 1
    target=guest("nodeb",905,"target")
    primary=guest("nodea",902,"source")
    security=guest("nodea",906,"source")
    if any(x is None for x in (target,primary,security)):
        print("JNS_DASH_PRIVATE_STAGE_BLOCKED=guest_read_failed")
        return 1
    try:
        active={e["url_path"] for e in target["items"]}
        seen=set()
        missing=[]
        for vm,source in ((902,primary),(906,security)):
            for e in source["items"]:
                path=e["url_path"]
                if path not in active and path not in seen:
                    missing.append({"vm":vm,"record":e})
                    seen.add(path)
    except (KeyError,TypeError):
        print("JNS_DASH_PRIVATE_STAGE_BLOCKED=invalid_dashboard_index")
        return 1
    payload=json.dumps({"target_vm":905,"source_vms":[902,906],
                        "missing":missing},separators=(",",":"))
    code=base64.b64encode(STAGE.encode()).decode()
    dest=ssh("nodeb",["python3","-u","-c",
        "exec(__import__('base64').b64decode('"+code+"'))"],70,payload)
    if not dest or dest.returncode:
        print("JNS_DASH_PRIVATE_STAGE_BLOCKED=private_host_write_failed")
        return 1
    safe=[x for x in dest.stdout.splitlines() if x.startswith("JNS_DASH_PRIVATE_STAGE_OK=")]
    if len(safe)!=1:
        print("JNS_DASH_PRIVATE_STAGE_BLOCKED=no_success_attestation")
        return 1
    print(safe[0],flush=True)
    print("JNS_HA_CONFIG_AND_CONTROL_UNCHANGED=yes",flush=True)
    return 0

if __name__=="__main__":
    raise SystemExit(main())
