#!/usr/bin/env python3
"""Read-only Node B MQTT/Zigbee2MQTT LXC migration gate to Node A.
No IP, MAC, credentials, raw container config or service data is published.
"""
import base64,json,shlex,subprocess
REMOTE=r'''
import json,re,subprocess
from pathlib import Path
HOST="__HOST__"
def run(cmd,t=12):
 try:p=subprocess.run(cmd,capture_output=True,text=True,timeout=t)
 except (OSError,subprocess.TimeoutExpired):return None
 return p if p.returncode==0 else None
def ct(n):
 p=run(["pct","config",str(n)])
 status=run(["pct","status",str(n)])
 if not p:return {"exists":False}
 lines=p.stdout.splitlines()
 d={"exists":True,"running":bool(status and "running" in status.stdout)}
 for key in ("hostname","memory","swap","cores","onboot","unprivileged","ostype","features"):
  q=re.search("^"+key+r":\s*(\S+)",p.stdout,re.M)
  if q:
   v=q.group(1)
   if key in ("memory","swap","cores","onboot","unprivileged","ostype"):d[key]=v
   if key=="hostname":d["role"]="mqtt" if "mqtt" in v else "zigbee" if "zigbee" in v else "unknown"
 d["disk_storage_types"]=[]
 d["has_bind_mounts"]=False
 d["passthrough_keys"]=[]
 for line in lines:
  m=re.match(r"^(rootfs|mp\d+):\s*(.+)$",line)
  if m:
   val=m.group(2)
   d["disk_storage_types"].append({"key":m.group(1),"storage":val.split(":",1)[0] if ":" in val else "host_path","has_size":"size=" in val})
   if val.startswith("/"):d["has_bind_mounts"]=True
  m=re.match(r"^(lxc\.(mount|device|cgroup)|dev\d+):",line)
  if m:d["passthrough_keys"].append(m.group(1))
 return d
def capacity():
 p=run(["df","-Pk","/var/lib/vz/dump"])
 if not p:return None
 rows=p.stdout.splitlines()
 if len(rows)<2:return None
 try:return round(int(rows[-1].split()[3])/1048576,2)
 except (ValueError,IndexError):return None
out={"host":HOST,"storage_local_dump_free_gib":capacity()}
if HOST=="nodeb":
 out["sources"]={str(n):ct(n) for n in (212,214)}
 for n in (212,214):
  p=run(["pct","config",str(n)])
  # active named/independent external mounts may need separate migration
  out["source_"+str(n)+"_mount_count"]=len(re.findall(r"^mp\d+:",p.stdout,re.M)) if p else None
if HOST=="nodea":
 out["destinations"]={str(n):ct(n) for n in (230,231,212,214)}
 p=run(["zfs","list","-H","-o","available","vmdata"])
 out["vmdata_available"]=p.stdout.strip() if p else None
print("JNS_CT_MIGRATION_JSON="+json.dumps(out,sort_keys=True))
'''
def audit(host):
 code=REMOTE.replace("__HOST__",host)
 encoded=base64.b64encode(code.encode()).decode()
 cmd=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes",
 "-o","ConnectTimeout=6",host,shlex.join(["python3","-c","exec(__import__('base64').b64decode('"+encoded+"'))"])]
 try:p=subprocess.run(cmd,capture_output=True,text=True,timeout=35)
 except (OSError,subprocess.TimeoutExpired):return {"status":"ssh_timeout"}
 if p.returncode:return {"status":"not_available"}
 lines=[x for x in p.stdout.splitlines() if x.startswith("JNS_CT_MIGRATION_JSON=")]
 if not lines:return {"status":"missing_payload"}
 try:return {"status":"ok",**json.loads(lines[-1].split("=",1)[1])}
 except ValueError:return {"status":"invalid_payload"}
if __name__=="__main__":
 print("JNS_SOLAR_CT_MIGRATION_PREFLIGHT_READONLY")
 for host in ("nodea","nodeb"):
  print(host+"="+json.dumps(audit(host),sort_keys=True))
 print("JNS_SOLAR_CT_MIGRATION_PREFLIGHT_COMPLETE")
