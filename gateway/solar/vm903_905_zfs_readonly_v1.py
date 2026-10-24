#!/usr/bin/env python3
"""Read-only VM903/905 disk identity and cold staging preflight.
Never exports NIC/MAC, drive image contents, credentials or private paths.
"""
import base64,json,shlex,subprocess
REMOTE=r'''
import json,os,re,subprocess
role="__ROLE__"
data={"role":role}
def run(argv,seconds=18):
 try:p=subprocess.run(argv,capture_output=True,text=True,timeout=seconds)
 except (OSError,subprocess.TimeoutExpired):return None
 return p if p.returncode==0 else None
for vm in (903,905):
 p=run(["qm","config",str(vm)])
 status=run(["qm","status",str(vm)])
 d={"exists":bool(p),"running":bool(status and "running" in status.stdout)}
 if p:
  rows=p.stdout.splitlines()
  for key in ("name","memory","balloon","cores","onboot","bios","machine","agent"):
   m=re.search(r"^"+key+r":\s*(\S+)",p.stdout,re.M)
   if m and key!="name":d[key]=m.group(1)
   if m and key=="name":d["role_name"]="ha-general" if "general" in m.group(1) else "plant" if "plant" in m.group(1) else "other"
  d["disk_volumes"]=[]
  d["device_keys"]=[]
  for row in rows:
   m=re.match(r"^(scsi\d+|virtio\d+|sata\d+|ide\d+|efidisk\d+|tpmstate\d+|unused\d+):\s*(.*)",row)
   if m:
    key,volume=m.groups()
    token=volume.split(",",1)[0]
    storage=token.split(":",1)[0] if ":" in token else "path_or_iso"
    name=token.split(":",1)[1] if ":" in token else ""
    size=re.search(r"(?:^|,)size=([^,\s]+)",volume)
    d["disk_volumes"].append({"key":key,"storage":storage,"volume":name if re.fullmatch(r"(vm-\d+-disk-\d+|base-\d+-disk-\d+)",name) else "nonstandard","size":size.group(1) if size else "unknown","media_cdrom":"media=cdrom" in volume})
   pdev=re.match(r"^(usb\d+|hostpci\d+|serial\d+|args):",row)
   if pdev:d["device_keys"].append(pdev.group(1))
 data[str(vm)]=d
if role=="nodeb":
 for vm in (903,905):
  for d in data[str(vm)].get("disk_volumes",[]):
   if d["storage"]=="vmdata" and d["volume"]!="nonstandard":
    z=run(["zfs","list","-Hp","-o","type,referenced","vmdata/"+d["volume"]])
    if z:
     p=z.stdout.strip().split()
     if len(p)==2:
      d["zfs_type"]=p[0]
      try:d["referenced_gib"]=round(int(p[1])/1073741824,2)
      except ValueError:pass
print("JNS_VM_DISK_GATE_JSON="+json.dumps(data,sort_keys=True))
'''
def probe(host):
 code=REMOTE.replace("__ROLE__",host)
 encoded=base64.b64encode(code.encode()).decode()
 cmd=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=5",host,
      shlex.join(["python3","-c","exec(__import__('base64').b64decode('"+encoded+"'))"])]
 try:p=subprocess.run(cmd,capture_output=True,text=True,timeout=45)
 except (OSError,subprocess.TimeoutExpired):return {"status":"timeout"}
 if p.returncode:return {"status":"failure"}
 lines=[x for x in p.stdout.splitlines() if x.startswith("JNS_VM_DISK_GATE_JSON=")]
 if not lines:return {"status":"missing_output"}
 try:return json.loads(lines[-1].split("=",1)[1])
 except ValueError:return {"status":"bad_output"}
if __name__=="__main__":
 print("JNS_SOLAR_VM905_VM903_PRECHECK_READONLY")
 for host in ("nodea","nodeb"):print(host+"="+json.dumps(probe(host),sort_keys=True))
 print("JNS_SOLAR_VM905_VM903_PRECHECK_DONE")
