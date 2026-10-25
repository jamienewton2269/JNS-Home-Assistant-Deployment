#!/usr/bin/env python3
"""Solar VM906 relocation: source destination health and supported privilege audit.
Read-only; never output identities, credentials, raw configs or network addresses.
"""
import json,os,pathlib,subprocess,shlex
def cmd(argv,timeout=12):
 try:return subprocess.run(argv,capture_output=True,text=True,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):return None
def nodec():
 d={"host":os.uname().nodename.split(".")[0]}
 for c in (906,909):
  p=cmd(["qm","status",str(c)])
  d["qm_"+str(c)+"_state"]=p.stdout.strip() if p and p.returncode==0 else "unavailable"
 for r in ("/etc/pve/nodes/nodec/qemu-server/906.conf","/dev/pve/vm-906-disk-1"):
  d["path_"+("906conf" if r.endswith(".conf") else "906vol")+"_present"]=pathlib.Path(r).exists()
 p=cmd(["sudo","-n","-l"])
 d["gateway_sudo_available"]=bool(p and p.returncode==0 and "jns-gateway-exec" in p.stdout)
 d["vm_commands_directly_allowed"]=bool(p and p.returncode==0 and ("NOPASSWD: ALL" in p.stdout or "/usr/sbin/qm" in p.stdout))
 mount=pathlib.Path("/mnt/pve/nfs-ct")
 p=cmd(["findmnt","-rn","-M",str(mount)])
 d["nfs_mount_present"]=bool(p and p.returncode==0)
 if d["nfs_mount_present"]:
  v=os.statvfs(mount)
  d["nfs_free_gib"]=round(v.f_bavail*v.f_frsize/1073741824,1)
 d["nfs_runner_writable"]=os.access(mount,os.W_OK)
 # Only list preexisting backup metadata of vm906, never open/log content.
 backup=mount/"dump"
 try:
  hits=[x for x in backup.glob("vzdump-qemu-906-*.vma.zst") if x.is_file()]
  d["older_906_backup_count"]=len(hits)
 except OSError:d["older_906_backup_count"]="unknown"
 p=cmd(["systemctl","is-active","jns-management-bridge.service"])
 d["bridge_active"]=bool(p and p.stdout.strip()=="active")
 return d
def nodea():
 src=r'''
set -eu
test "$(hostname -s)" = nodea
echo "VM906_COLLISION=$(qm config 906 >/dev/null 2>&1 && echo yes || echo no)"
echo "VM900_STATE=$(qm status 900 2>/dev/null | awk '{print $2}')"
free -m | awk '/^Mem:/ {print "MEM_AVAILABLE_MB="$7;print "MEM_TOTAL_MB="$2} /^Swap:/ {print "SWAP_USED_MB="$3}'
zfs list -Hp -o available vmdata | awk '{print "VMDATA_FREE_GIB="int($1/1073741824)}'
ps -eo comm | grep -q '^vzdump$' && echo "VZDUMP_ACTIVE=yes" || echo "VZDUMP_ACTIVE=no"
'''
 p=cmd(["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=5","nodea",shlex.join(["bash","-c",src])],25)
 if not p or p.returncode:return {"status":"trusted_nodea_unavailable"}
 keys={"VM906_COLLISION","VM900_STATE","MEM_AVAILABLE_MB","MEM_TOTAL_MB","SWAP_USED_MB","VMDATA_FREE_GIB","VZDUMP_ACTIVE"}
 d={"status":"ok"}
 for l in p.stdout.splitlines():
  if "=" in l:
   k,v=l.split("=",1)
   if k in keys:d[k]=v[:30]
 return d
print("JNS_SOLAR_HA_SECURITY_MIGRATION_CAPACITY_AUDIT")
print("NODEC="+json.dumps(nodec(),sort_keys=True))
print("NODEA="+json.dumps(nodea(),sort_keys=True))
print("END_READONLY")
