#!/usr/bin/env python3
"""Read-only Proxmox and HA backup recovery preflight. No snapshots/backups made."""
import json,subprocess,shlex,time
def ssh(host,commands,timeout=25):
 p=subprocess.run(["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes",host,shlex.join(commands)],capture_output=True,text=True,timeout=timeout)
 return p.returncode,p.stdout,p.stderr
def guest(host,vm,args,timeout=45):
 rc,out,err=ssh(host,["qm","guest","exec",str(vm),"--",*args],timeout=timeout)
 if rc: return rc,"",err[-200:]
 d=json.loads(out); pid=d.get("pid")
 for _ in range(timeout):
  if d.get("exited"):break
  if not pid:break
  time.sleep(1)
  rc, out,err=ssh(host,["qm","guest","exec-status",str(vm),str(pid)],timeout=20)
  if rc:return rc,"",err[-200:]
  d=json.loads(out)
 return d.get("exitcode",99),d.get("out-data",""),d.get("err-data","")
print("JNS_BACKUP_PROXMOX_RECOVERY_PREFLIGHT_START",flush=True)
for name,host,vm in (("GENERAL","nodeb",905),("PRIMARY","nodea",902)):
 print("===TARGET",name,host,vm,"===",flush=True)
 for label,command in [
  ("VM_SNAPSHOTS",["qm","listsnapshot",str(vm)]),
  ("HOST_RAM",["free","-m"]),
  ("HOST_STORAGE",["pvesm","status"]),
  ("HOST_VM_CONFIG",["qm","config",str(vm)]),
 ]:
  try:
   rc,out,err=ssh(host,command,timeout=30)
   if label=="HOST_VM_CONFIG":
    out="\n".join(x for x in out.splitlines() if x.startswith(("memory:","balloon:","scsi0:","cores:","onboot:","agent:","name:")))
   if label=="HOST_STORAGE":
    out="\n".join(out.splitlines()[:15])
   print(label,"RC",rc,"OUT",out[:3000],"ERR",err[-200:],flush=True)
  except Exception as e:print(label,"ERROR",type(e).__name__,str(e)[:100],flush=True)
 for label,command in [
  ("BACKUP_NEW_HELP",["ha","backups","new","--help"]),
  ("BACKUP_INFO_HELP",["ha","backups","info","--help"]),
  ("BACKUP_DIR_SPACE",["df","-h","/backup","/mnt/data"]),
  ("BACKUP_DIR_SIZE",["du","-sh","/backup"]),
 ]:
  try:
   rc,out,err=guest(host,vm,command)
   print(label,"RC",rc,"OUT",out[:2500],"ERR",err[-160:],flush=True)
  except Exception as e:print(label,"ERROR",type(e).__name__,str(e)[:120],flush=True)
print("JNS_BACKUP_RECOVERY_PREFLIGHT_COMPLETE_NO_WRITES",flush=True)
