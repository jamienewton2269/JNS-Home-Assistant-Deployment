#!/usr/bin/env python3
"""Read-only HA900 full-backup location gate (source capacity and destination
NAS writable indicators; NEVER writes a backup or mounts any share).
No remote share endpoint, CIFS credentials, data or paths in public logs.
"""
import base64,json,shlex,subprocess
PROBE=r'''
import json,os,subprocess
from pathlib import Path
host=os.uname().nodename.split(".")[0]
result={"host":host,"audit":"solar-vm900-backup-capacity-v1"}
def run(argv,secs=8):
 try:
  p=subprocess.run(argv,capture_output=True,text=True,timeout=secs)
  return p.returncode,p.stdout
 except (OSError,subprocess.TimeoutExpired):return 125,""
for label,path in [("NAS","/mnt/pve/NAS"),("WD_BACKUP","/mnt/pve/WD-BACKUP")]:
 code,mnt=run(["findmnt","-rn","-M",path,"-o","FSTYPE"])
 result[label+"_mounted"]=code==0
 result[label+"_type"]=mnt.strip() if code==0 and mnt.strip() in ("cifs","nfs","nfs4") else "unknown"
 if code==0:
  r,d=run(["df","-Pk",path])
  if r==0:
   lines=d.splitlines()
   if len(lines)>=2:
    bits=lines[-1].split()
    if len(bits)>=4:
     try:result[label+"_free_gib"]=round(int(bits[3])/1048576,1)
     except ValueError:pass
if host=="nodea":
 for dataset in ("vmdata",):
  code,rows=run(["zfs","list","-H","-o","available","-t","filesystem",dataset])
  if code==0 and rows.strip():result["vmdata_space_human"]=rows.strip()[:20]
  code,rows=run(["zfs","get","-H","-o","value","mountpoint",dataset])
  if code==0 and rows.strip():
   path=rows.strip()
   result["vmdata_mount_exists"]=Path(path).is_dir()
 code,state=run(["qm","status","900"])
 result["vm900_running"]=code==0 and "running" in state
 code,conf=run(["qm","config","900"])
 result["vm900_snapshot_capability_pending"]=code==0
print("VM900_BACKUP_SITE_JSON="+json.dumps(result,sort_keys=True))
'''
def probe(host):
  encoded=base64.b64encode(PROBE.encode()).decode()
  try:
    p=subprocess.run(["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes",
       "-o","ConnectTimeout=6",host,shlex.join(["python3","-c","exec(__import__('base64').b64decode('"+encoded+"'))"])],
       capture_output=True,text=True,timeout=20)
  except (OSError,subprocess.TimeoutExpired):return {"status":"transport_timeout"}
  if p.returncode:return {"status":"unavailable"}
  r=[x for x in p.stdout.splitlines() if x.startswith("VM900_BACKUP_SITE_JSON=")]
  if not r:return {"status":"no_result"}
  try:return {"status":"ok",**json.loads(r[-1].split("=",1)[1])}
  except ValueError:return {"status":"invalid_response"}
print("JNS_VM900_BACKUP_SPACE_PREFLIGHT_READONLY")
for h in ("nodea","nodeb"):
 print(h+"="+json.dumps(probe(h),sort_keys=True))
print("JNS_VM900_BACKUP_SPACE_PREFLIGHT_COMPLETE")
