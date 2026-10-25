#!/usr/bin/env python3
"""Read-only final HA900 cold-archive gate. No guest starts, stops or backups.
Safely reports only the storage and VM properties required for archiving.
"""
import json,os,subprocess,shlex,stat
SSH=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=6"]
SCRIPT=r'''
import json,subprocess,os,re
def r(cmd,timeout=12):
 try:
  p=subprocess.run(cmd,capture_output=True,text=True,timeout=timeout)
  return p.returncode,p.stdout
 except (OSError,subprocess.TimeoutExpired):return 255,""
if os.uname().nodename.split(".")[0]!="nodea":raise SystemExit(70)
d={"status":"ok"}
rc,out=r(["qm","status","900"]);d["stopped"]=rc==0 and out.strip()=="status: stopped"
rc,config=r(["qm","config","900"])
d["config_available"]=rc==0
d["name_matches"]=bool(re.search(r"^name:\s+homeassistant-recovery\s*$",config,re.M))
d["onboot_disabled"]=bool(re.search(r"^onboot:\s+0\s*$",config,re.M))
d["configured_disks"]=[]
for line in config.splitlines():
 m=re.match(r"^(efidisk\d+|scsi\d+|virtio\d+|sata\d+|tpmstate\d+):\s+([^,\s]+)",line)
 if m:
  key,token=m.groups()
  if ":" in token:
   store,name=token.split(":",1)
   d["configured_disks"].append({"slot":key,"store":store,"dataset_name":name if re.fullmatch(r"vm-900-disk-\d+",name) else "nonstandard"})
for x in d["configured_disks"]:
 if x["store"]=="vmdata" and x["dataset_name"]!="nonstandard":
  rc,out=r(["zfs","list","-Hp","-o","type,used,referenced,volsize","vmdata/"+x["dataset_name"]])
  parts=out.split()
  if rc==0 and len(parts)>=4:
   x["zfs_type"]=parts[0]
   x["used_bytes"]=int(parts[1])
   x["referenced_bytes"]=int(parts[2])
   x["logical_bytes"]=int(parts[3])
rc,out=r(["zfs","get","-H","-o","value","mountpoint","vmdata"]);d["vmdata_mount_known"]=rc==0 and out.strip() not in ("none","legacy","-")
rc,out=r(["zfs","list","-Hp","-o","available","vmdata"])
d["vmdata_free_gib"]=round(int(out.strip())/1073741824,1) if rc==0 and out.strip().isdigit() else None
rc,out=r(["bash","-c","command -v vzdump >/dev/null; command -v zstd >/dev/null; command -v vma >/dev/null"])
d["native_backup_tools_available"]=rc==0
rc,out=r(["bash","-c","command -v zstreamdump >/dev/null"])
d["zstreamdump_available"]=rc==0
rc,out=r(["bash","-c","command -v zfs >/dev/null"])
d["zfs_available"]=rc==0
print("HA900_NODEA_PREFLIGHT="+json.dumps(d,sort_keys=True))
'''
def main():
 print("HA900_NFS_ARCHIVE_GATE")
 try:
  p=subprocess.run(SSH+["nodea",shlex.join(["python3","-c",SCRIPT])],capture_output=True,text=True,timeout=35)
  lines=[x for x in p.stdout.splitlines() if x.startswith("HA900_NODEA_PREFLIGHT=")]
  a=json.loads(lines[-1].split("=",1)[1]) if p.returncode==0 and lines else {"status":"inaccessible"}
 except (OSError,subprocess.TimeoutExpired,ValueError):a={"status":"inaccessible"}
 print("NODEA="+json.dumps(a,sort_keys=True))
 n={"host":os.uname().nodename.split(".")[0]}
 n["nfs_mounted"]=subprocess.run(["findmnt","-rn","-M","/mnt/pve/nfs-ct"],capture_output=True).returncode==0
 if n["nfs_mounted"]:
  try:
   s=os.statvfs("/mnt/pve/nfs-ct")
   n["nfs_free_gib"]=round(s.f_bavail*s.f_frsize/1073741824,1)
  except OSError:n["nfs_free_gib"]=None
 n["nfs_runner_writable"]=os.access("/mnt/pve/nfs-ct",os.W_OK)
 for exe in ["zstd","zstreamdump","vma","sha256sum"]:
  n["has_"+exe]=subprocess.run(["bash","-c","command -v "+exe],capture_output=True).returncode==0
 print("NODEC="+json.dumps(n,sort_keys=True))
 print("HA900_NFS_ARCHIVE_GATE_COMPLETE")
if __name__=="__main__":main()
