#!/usr/bin/env python3
"""Safe metadata-only inspection of the already existing VM902 staging directory."""
import base64,json,shlex,subprocess
SRC=r'''
import json,os,time
from pathlib import Path
p=Path("/var/lib/jns-solar/ha-p0-primary-lite-902/jns-vm902-consolidation-20261027-v1")
o={"stage_exists":p.is_dir(),"stage_symlink":p.is_symlink()}
if p.is_dir() and not p.is_symlink():
 for key,name in (("config","vm902-proxmox.conf"),("manifest","MANIFEST.json"),("private_log","private-vzdump.log")):
  f=p/name
  o[key+"_exists"]=f.is_file() and not f.is_symlink()
  if key=="private_log" and f.is_file():
   # Count log lines; do not disclose internal URLs/paths/credentials.
   try:
    lines=f.read_text(errors="replace").splitlines()
    o["log_lines"]=len(lines)
    o["log_completed"]=any("Finished Backup of VM 902" in x for x in lines)
    o["log_backup_error"]=any("ERROR:" in x or "TASK ERROR" in x for x in lines)
   except OSError:pass
 archives=[f for f in p.glob("vzdump-qemu-902-*.vma.zst") if f.is_file() and not f.is_symlink()]
 o["archives_count"]=len(archives)
 if len(archives)==1:
  f=archives[0];o["archive_mib"]=round(f.stat().st_size/1048576,1);o["archive_age_minutes"]=round((time.time()-f.stat().st_mtime)/60,1)
print("JNS_VM902_STAGE_READONLY="+json.dumps(o,sort_keys=True))
'''
def main():
 s=base64.b64encode(SRC.encode()).decode()
 p=subprocess.run(["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=6","nodea",shlex.join(["python3","-c","exec(__import__('base64').b64decode('"+s+"'))"])],capture_output=True,text=True,timeout=32)
 v=[x for x in p.stdout.splitlines() if x.startswith("JNS_VM902_STAGE_READONLY=")]
 print(v[0] if p.returncode==0 and len(v)==1 else "JNS_VM902_STAGE_AUDIT=unavailable")
 print("JNS_NO_STATE_CHANGED=yes")
if __name__=="__main__":main()
