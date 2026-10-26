#!/usr/bin/env python3
"""Read-only evacuation backup coverage and storage mounts from JNS GitHub runner.
No credentials, network paths, archive names or guest config content logged.
Presence != tested restore. Does not create snapshots, backups or change VM state.
"""
import base64,json,os,pathlib,shlex,subprocess,time
ROOTS=["/var/lib/vz/dump","/mnt/pve/NAS/dump","/mnt/pve/WD-BACKUP/dump","/mnt/pve/nfs-ct/dump"]
REMOTE=r'''
import json,os,pathlib,re,subprocess,time
host=os.uname().nodename.split(".")[0]
roots=["/var/lib/vz/dump","/mnt/pve/NAS/dump","/mnt/pve/WD-BACKUP/dump","/mnt/pve/nfs-ct/dump"]
def run(args,timeout=8):
 try:return subprocess.run(args,capture_output=True,text=True,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):return None
def list_ids(command):
 p=run(command)
 if not p or p.returncode:return []
 o=[]
 for ln in p.stdout.splitlines()[1:]:
  parts=ln.split()
  if parts and parts[0].isdigit():o.append(int(parts[0]))
 return sorted(set(o))
guest={"vm":list_ids(["qm","list"]),"ct":list_ids(["pct","list"])}
report={"host":host,"guest_ids":guest,"mounted_archives":{},"backup_counts":{}}
for root in roots:
 mount="/".join(root.split("/")[:4]) if root.startswith("/mnt/pve/") else "/"
 p=run(["findmnt","-rn","-M",mount,"-o","FSTYPE"])
 mounted=bool(p and p.returncode==0)
 record={"mounted":mounted}
 if not mounted and mount!="/":
  report["mounted_archives"][root.replace("/mnt/pve/","").replace("/dump","")]=record
  continue
 try:
  folder=pathlib.Path(root)
  record["folder_exists"]=folder.is_dir()
  if folder.is_dir():
   count_by_type={"vm":0,"ct":0}
   checked=[]
   for f in folder.glob("vzdump-*"):
    if not f.is_file() or f.is_symlink():continue
    m=re.match(r"vzdump-(qemu|lxc)-(\d+)-.+\.(vma|tar)\.(zst|gz|lzo)$",f.name)
    if not m:continue
    kind="vm" if m.group(1)=="qemu" else "ct"
    count_by_type[kind]+=1
    idn=int(m.group(2))
    if idn in guest[kind]:
     checked.append({"kind":kind,"id":idn,
        "size_mib":round(f.stat().st_size/1048576,1),
        "age_days":round((time.time()-f.stat().st_mtime)/86400,1)})
   record["file_count"]=count_by_type
   # For each guest only show age and size of most recent matching backup.
   latest={}
   for x in checked:
    key=x["kind"]+str(x["id"])
    if key not in latest or x["age_days"]<latest[key]["age_days"]:
     latest[key]=x
   record["latest_guest_backups"]=list(latest.values())
 except (OSError,PermissionError):record["folder_access"]="restricted"
 report["mounted_archives"][root.replace("/mnt/pve/","").replace("/dump","")]=record
print("JNS_SAFE_BACKUP_AUDIT="+json.dumps(report,sort_keys=True))
'''
def fetch(host):
 source=base64.b64encode(REMOTE.encode()).decode()
 cmd=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes",
 "-o","ConnectTimeout=6",host,
 shlex.join(["python3","-c","exec(__import__('base64').b64decode('"+source+"'))"])]
 try:r=subprocess.run(cmd,capture_output=True,text=True,timeout=45)
 except (OSError,subprocess.TimeoutExpired):return {"host":host,"reachable":False}
 if r.returncode:return {"host":host,"reachable":False}
 a=[s.split("=",1)[1] for s in r.stdout.splitlines() if s.startswith("JNS_SAFE_BACKUP_AUDIT=")]
 if len(a)!=1:return {"host":host,"readable":False}
 try:return json.loads(a[0])
 except ValueError:return {"host":host,"valid":False}
def main():
 print("JNS_CLUSTER_EVICTION_BACKUP_GATE")
 for host in ("nodea","nodeb"):
  print("NODE_"+host.upper()+"="+json.dumps(fetch(host),sort_keys=True))
 root=pathlib.Path("/mnt/pve/nfs-ct")
 p=subprocess.run(["findmnt","-rn","-M",str(root)],capture_output=True,text=True)
 result={"host":"nodec","nfs_mount_ok":p.returncode==0}
 if p.returncode==0:
  st=os.statvfs(root)
  result["nfs_free_gib"]=round(st.f_bavail*st.f_frsize/1073741824,1)
  paths=[root/"dump",root/"JNS-Solar-Archives"]
  for path in paths:
   try:result["archive_"+path.name+"_visible"]=path.is_dir()
   except PermissionError:result["archive_"+path.name+"_visible"]="restricted"
 print("NODE_NODEC="+json.dumps(result,sort_keys=True))
 print("JNS_CLUSTER_EVICTION_BACKUP_GATE_DONE")
if __name__=="__main__":main()
