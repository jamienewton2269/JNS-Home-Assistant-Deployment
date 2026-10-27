#!/usr/bin/env python3
"""Read-only private status check for current JNS HA consolidation archives.
Only sanitized booleans, archive size/age and headroom; no paths, configs or identifiers.
"""
import base64,json,os,shlex,subprocess
REMOTE=r'''
import json,os,subprocess,time
from pathlib import Path
host=os.uname().nodename.split(".")[0]
out={"host":host}
def run(args,timeout=10):
 try:return subprocess.run(args,capture_output=True,text=True,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):return None
def free(path):
 p=run(["df","-Pk",str(path)])
 try:return round(int(p.stdout.splitlines()[-1].split()[3])/1048576,1) if p and p.returncode==0 else None
 except (ValueError,IndexError):return None
out["root_free_gib"]=free("/")
p=run(["free","-m"])
try:out["ram_available_mib"]=next(int(r.split()[6]) for r in p.stdout.splitlines() if r.startswith("Mem:"))
except (StopIteration,ValueError,IndexError,AttributeError):out["ram_available_mib"]=None
if host=="nodeb":
 path=Path("/mnt/pve/NAS/dump/jns-ha-general-consolidation-20261027-v1")
 mounted=run(["findmnt","-n","-M","/mnt/pve/NAS"])
 out["archive_mount_active"]=bool(mounted and mounted.returncode==0)
 out["archive_dir_exists"]=path.is_dir() and not path.is_symlink()
 out["archive_mount_free_gib"]=free("/mnt/pve/NAS") if out["archive_mount_active"] else None
 if out["archive_dir_exists"]:
  archives=[x for x in path.glob("vzdump-qemu-905-*.vma.zst") if x.is_file() and not x.is_symlink()]
  out["archive_count"]=len(archives)
  if archives:
   archive=max(archives,key=lambda x:x.stat().st_size)
   out["archive_size_mib"]=round(archive.stat().st_size/1048576,1)
   out["archive_last_changed_sec"]=round(time.time()-archive.stat().st_mtime,1)
  out["manifest_verified_file_exists"]=(path/"MANIFEST.json").is_file()
  out["private_log_exists"]=(path/"vzdump-private.log").is_file()
 q=run(["qm","status","905"])
 out["vm905_running"]=bool(q and q.returncode==0 and q.stdout.strip()=="status: running")
if host=="nodea":
 q=run(["qm","status","902"])
 c=run(["qm","config","902"])
 out["vm902_running"]=bool(q and q.returncode==0 and q.stdout.strip()=="status: running")
 out["vm902_config_readable"]=bool(c and c.returncode==0)
 out["vm902_disk_expected"]=bool(c and c.returncode==0 and "scsi0: vmdata:vm-902-disk-1," in c.stdout)
 out["vm902_agent_enabled"]=bool(c and c.returncode==0 and "agent: enabled=1" in c.stdout)
print("JNS_BACKUP_LIVE_STATE="+json.dumps(out,sort_keys=True))
'''
def main():
 print("JNS_BACKUP_LIVE_READONLY_BEGIN",flush=True)
 for host in ("nodea","nodeb"):
  b64=base64.b64encode(REMOTE.encode()).decode()
  cmd=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes",
       "-o","ConnectTimeout=6",host,shlex.join(["python3","-c",
        "exec(__import__('base64').b64decode('"+b64+"'))"])]
  try:p=subprocess.run(cmd,text=True,capture_output=True,timeout=40)
  except (OSError,subprocess.TimeoutExpired):
   print("JNS_BACKUP_LIVE="+json.dumps({"host":host,"access":"unavailable"}));continue
  lines=[x for x in p.stdout.splitlines() if x.startswith("JNS_BACKUP_LIVE_STATE=")]
  if p.returncode==0 and len(lines)==1:
   print(lines[0].replace("JNS_BACKUP_LIVE_STATE=","JNS_BACKUP_LIVE="),flush=True)
  else:print("JNS_BACKUP_LIVE="+json.dumps({"host":host,"access":"unavailable"}),flush=True)
 print("JNS_NO_PRODUCTION_STATE_CHANGED=yes",flush=True)
if __name__=="__main__":main()
