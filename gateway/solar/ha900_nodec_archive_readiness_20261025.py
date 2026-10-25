#!/usr/bin/env python3
"""Read-only HA900 -> Node C archival placement readiness.
No guest bytes, credentials, storage endpoint names, private file paths
or identity keys emitted. NodeC runner unprivileged; Node A root over pinned SSH.
"""
import json,os,shlex,subprocess,stat
SSH=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=5"]
def remote(host, script, timeout=28):
 try:
  p=subprocess.run(SSH+[host,shlex.join(["bash","-c",script])],capture_output=True,text=True,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):return {"status":"ssh_timeout"}
 if p.returncode:return {"status":"ssh_or_command_error","exit_code":p.returncode}
 return {"status":"ok","output":p.stdout}
def nodea():
 s=r'''
set -Eeuo pipefail
test "$(hostname -s)" = nodea
echo "VM_STATE=$(qm status 900 | cut -d' ' -f2)"
echo "ONBOOT=$(qm config 900 | sed -n 's/^onboot: //p')"
for n in 0 1; do
 dataset="vmdata/vm-900-disk-$n"
 if zfs list -H "$dataset" >/dev/null 2>&1; then
   echo "DISK_$n=$(zfs list -Hp -o type,referenced,used,volsize "$dataset" | tr '\\t' ',')"
 fi
done
echo "NODEC_ROOT_SSH_ACCESS=$(ssh -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=5 root@nodec 'test "$(hostname -s)" = nodec' >/dev/null 2>&1 && echo yes || echo no)"
if test -d /mnt/pve/nfs-ct; then
  echo "NODEA_NFS_CT_MOUNTED=$(findmnt -rn -M /mnt/pve/nfs-ct -o FSTYPE 2>/dev/null || echo no)"
fi
'''
 p=remote("nodea",s,28)
 if p.get("status")!="ok":return p
 out={}
 for line in p.pop("output").splitlines():
  if "=" not in line:continue
  k,v=line.split("=",1)
  if k in ("VM_STATE","ONBOOT","NODEC_ROOT_SSH_ACCESS","NODEA_NFS_CT_MOUNTED"):out[k]=v[:30]
  elif k.startswith("DISK_"):out[k]=v[:160]
 return {**p,**out}
def nodec():
 d={"host":os.uname().nodename.split(".")[0]}
 d["vm909_config_visible"]=os.path.exists("/etc/pve/nodes/nodec/qemu-server/909.conf")
 path="/etc/pve/nodes/nodec/qemu-server/909.conf"
 d["vm909_config_readable_by_runner"]=os.access(path,os.R_OK)
 for label,p in [("nfs_ct","/mnt/pve/nfs-ct"),("nodec_root","/")]:
  try:
   v=os.statvfs(p)
   d[label+"_capacity_gib"]=round(v.f_blocks*v.f_frsize/2**30,1)
   d[label+"_free_gib"]=round(v.f_bavail*v.f_frsize/2**30,1)
   d[label+"_writable_by_runner"]=os.access(p,os.W_OK)
  except OSError:d[label+"_accessible"]=False
 d["nfs_ct_mount_active"]=subprocess.run(["findmnt","-rn","-M","/mnt/pve/nfs-ct"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0
 try:
  p=subprocess.run(["qm","config","909"],capture_output=True,text=True,timeout=8)
  if p.returncode==0:
   keys=[]
   for x in p.stdout.splitlines():
    k=x.split(":",1)[0]
    if k in ("scsi0","efidisk0","virtio0","sata0","unused0"):
     keys.append({"key":k,"store":"nfs-ct" if "nfs-ct:" in x else "local-lvm" if "local-lvm:" in x else "other","size":"256G" if "size=256G" in x else "other"})
   d["vm909_disk_metadata"]=keys
 except (OSError,subprocess.TimeoutExpired):d["vm909_disk_metadata"]="unavailable"
 return d
print("JNS_HA900_NODEC_ARCHIVE_READONLY")
print("NODEA="+json.dumps(nodea(),sort_keys=True))
print("NODEC="+json.dumps(nodec(),sort_keys=True))
print("JNS_HA900_NODEC_ARCHIVE_READONLY_COMPLETE")
