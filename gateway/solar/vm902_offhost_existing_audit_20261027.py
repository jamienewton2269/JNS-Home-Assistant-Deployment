#!/usr/bin/env python3
"""Read-only independent verification of existing VM902 off-host archive, no writes."""
import base64,json,os,shlex,subprocess,sys
CODE=r'''
import hashlib,json,os,re,subprocess
from pathlib import Path
p=Path("/mnt/pve/NAS/dump/jns-vm902-consolidation-20261027-v1")
o={"target_exists":p.is_dir(),"target_symlink":p.is_symlink()}
def sha(f):
 h=hashlib.sha256()
 with f.open("rb") as src:
  for chunk in iter(lambda:src.read(4*1024*1024),b""):h.update(chunk)
 return h.hexdigest()
try:
 if os.geteuid()!=0 or os.uname().nodename.split(".")[0]!="nodeb":raise ValueError("unauthorized")
 mount=subprocess.run(["findmnt","-n","-M","/mnt/pve/NAS"],capture_output=True,timeout=10)
 o["mount_ok"]=mount.returncode==0
 if not o["mount_ok"] or not o["target_exists"] or o["target_symlink"]:raise ValueError("target_unavailable")
 cfg=p/"vm902-proxmox.conf";mf=p/"MANIFEST.json"
 o["manifest_exists"]=mf.is_file() and not mf.is_symlink()
 o["config_exists"]=cfg.is_file() and not cfg.is_symlink()
 o["files_present"]=[x.name.split(".",1)[0] for x in p.iterdir() if x.is_file() and x.name in ("vm902-proxmox.conf","MANIFEST.json")]
 if not o["manifest_exists"]:raise ValueError("manifest_missing")
 m=json.loads(mf.read_text())
 name=m.get("name","")
 if not re.fullmatch(r"vzdump-qemu-902-[0-9_-]+\.vma\.zst",name):raise ValueError("archive_name_bad")
 a=p/name
 o["archive_exists"]=a.is_file() and not a.is_symlink()
 if not o["archive_exists"] or not o["config_exists"]:raise ValueError("incomplete")
 o["archive_mib"]=round(a.stat().st_size/1048576,1)
 if a.stat().st_size!=m.get("size"):raise ValueError("archive_size_mismatch")
 if sha(a)!=m.get("sha256") or sha(cfg)!=m.get("config_sha256"):raise ValueError("sha_mismatch")
 o["hash_verified"]=True
 z=subprocess.run(["zstd","-q","-t",str(a)],capture_output=True,timeout=950)
 if z.returncode:raise ValueError("zstd_invalid")
 o["zstd_verified"]=True
 o["offhost_verified"]=True
except (ValueError,OSError,subprocess.TimeoutExpired) as e:
 kind=str(e)
 o["offhost_verified"]=False
 o["incomplete_kind"]=kind if kind in ("unauthorized","target_unavailable","manifest_missing","archive_name_bad","incomplete","archive_size_mismatch","sha_mismatch","zstd_invalid") else "unavailable"
print("JNS_VM902_OFFHOST_AUDIT="+json.dumps(o,sort_keys=True))
'''
def main():
 if os.uname().nodename.split(".")[0]!="nodec":
  print("JNS_VM902_AUDIT_BLOCKED=wrong_runner");return 1
 source=base64.b64encode(CODE.encode()).decode()
 proc=subprocess.run(["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes",
   "-o","ConnectTimeout=6","nodeb",shlex.join(["python3","-u","-c",
     "exec(__import__('base64').b64decode('"+source+"'))"])],capture_output=True,text=True,timeout=1150)
 rows=[x for x in proc.stdout.splitlines() if x.startswith("JNS_VM902_OFFHOST_AUDIT=")]
 for row in rows[:1]:print(row,flush=True)
 print("JNS_VM902_NO_FILE_CHANGES=yes",flush=True)
 return 0 if proc.returncode==0 and len(rows)==1 else 1
if __name__=="__main__":sys.exit(main())
