#!/usr/bin/env python3
"""Back up production HA-General VM905 with native Proxmox; NEVER stop/reboot guest.
Runs from Node C existing authorised GitHub runner via Node B.
Only creates an independent snapshot archive under the currently mounted
Node B Proxmox NAS dump target. No configuration merge, guest update,
shutdown, restore, disk deletion or host cluster changes. Fail closed.
"""
import base64, json, os, shlex, subprocess, sys
SSH=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=6"]
TAG="jns-ha-general-consolidation-20261027-v1"
REMOTE=r'''
import hashlib,json,os,re,subprocess,sys,time
from pathlib import Path
TAG="jns-ha-general-consolidation-20261027-v1"
BASE=Path("/mnt/pve/NAS/dump")
OUT=BASE/TAG
def fail(code):
 print("JNS_HA_GENERAL_BACKUP_BLOCKED="+code,flush=True)
 raise SystemExit(71)
def run(cmd,timeout=18):
 try:return subprocess.run(cmd,capture_output=True,text=True,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):return None
if os.uname().nodename.split(".")[0]!="nodeb" or os.geteuid()!=0:fail("wrong_host_or_privilege")
m=run(["findmnt","-n","-M","/mnt/pve/NAS","-o","FSTYPE"])
if not m or m.returncode or not any(x in m.stdout.lower() for x in ("nfs","cifs","smb")):fail("backup_storage_not_mounted")
if not BASE.is_dir() or BASE.is_symlink():fail("invalid_backup_directory")
b=run(["df","-Pk",str(BASE)])
if not b or b.returncode:fail("backup_free_space_unknown")
try:free=int(b.stdout.splitlines()[-1].split()[3])
except (IndexError,ValueError):fail("backup_free_space_invalid")
if free<35*1048576:fail("backup_storage_below_35_gib")
b=run(["free","-m"])
if not b or b.returncode:fail("memory_unknown")
try:available=next(int(x.split()[6]) for x in b.stdout.splitlines() if x.startswith("Mem:"))
except (ValueError,StopIteration,IndexError):fail("memory_parse_failed")
if available<2100:fail("host_memory_pressure")
q=run(["qm","status","905"]);c=run(["qm","config","905"])
if not q or q.returncode or q.stdout.strip()!="status: running":fail("vm905_not_running")
if not c or c.returncode or not re.search(r"^name:\s*ha-s2-general\s*$",c.stdout,re.M):fail("unexpected_vm905_identity")
if re.search(r"^lock:",c.stdout,re.M):fail("vm905_locked")
if not re.search(r"^scsi0:\s*vmdata:vm-905-disk-1,",c.stdout,re.M):fail("unexpected_vm905_disk")
if re.search(r"^(?:usb\d+|hostpci\d+|virtiofs\d+|hookscript|args):",c.stdout,re.M):fail("unsupported_vm_passthrough")
if OUT.exists() or OUT.is_symlink():fail("tag_already_used")
OUT.mkdir(mode=0o700)
cfg=OUT/"vm905-proxmox.conf"
cfg.write_text(c.stdout)
os.chmod(cfg,0o600)
print("JNS_VM905_GUARDED_BACKUP_STARTED=yes",flush=True)
with (OUT/"vzdump-private.log").open("w") as log:
 try:
  p=subprocess.run(["vzdump","905","--mode","snapshot","--compress","zstd",
                    "--dumpdir",str(OUT),"--bwlimit","35000"],
                   stdout=log,stderr=subprocess.STDOUT,timeout=2800)
 except (OSError,subprocess.TimeoutExpired):fail("vzdump_unavailable_or_timeout")
if p.returncode:fail("vzdump_failed_inspect_private_log")
files=list(OUT.glob("vzdump-qemu-905-*.vma.zst"))
if len(files)!=1 or files[0].is_symlink():fail("expected_one_vm905_archive")
archive=files[0]
size=archive.stat().st_size
if not 1024*1024<size<45*1024**3:fail("invalid_archive_size")
test=run(["zstd","-q","-t",str(archive)],950)
if not test or test.returncode:fail("archive_zstd_integrity_failure")
def sha256(p):
 h=hashlib.sha256()
 with p.open("rb") as src:
  for chunk in iter(lambda:src.read(4*1024**2),b""):h.update(chunk)
 return h.hexdigest()
after=run(["qm","status","905"])
if not after or after.returncode or after.stdout.strip()!="status: running":fail("vm905_not_running_after_backup")
manifest={"vm":905,"source_host":"nodeb","mode":"proxmox_vzdump_snapshot",
          "archive_name":archive.name,"size_bytes":size,
          "archive_sha256":sha256(archive),
          "config_sha256":sha256(cfg),
          "zstd_test_passed":True,"restore_tested":False,
          "created_utc":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())}
with (OUT/"MANIFEST.json").open("x") as f:json.dump(manifest,f,sort_keys=True,indent=2);f.write("\n")
os.chmod(OUT/"MANIFEST.json",0o600)
print("JNS_VM905_BACKUP_VERIFIED="+json.dumps(
 {"size_bytes":size,"checksum_verified":True,"zstd_integrity":True,
  "vm_still_running":True,"restore_tested":False,
  "destination":"nodeb_mounted_nas_proxmox_dump"},sort_keys=True),flush=True)
'''
def main():
 if os.uname().nodename.split(".")[0]!="nodec":
  print("JNS_HA_GENERAL_BACKUP_BLOCKED=wrong_runner",flush=True)
  return 1
 token=base64.b64encode(REMOTE.encode()).decode()
 cmd=SSH+["nodeb",shlex.join(["python3","-u","-c",
       "exec(__import__('base64').b64decode('"+token+"'))"])]
 try:r=subprocess.run(cmd,capture_output=True,text=True,timeout=3400)
 except (OSError,subprocess.TimeoutExpired):
  print("JNS_HA_GENERAL_BACKUP_BLOCKED=transport_timeout",flush=True)
  return 1
 public=[line for line in r.stdout.splitlines() if
         line.startswith(("JNS_HA_GENERAL_BACKUP_BLOCKED=",
                          "JNS_VM905_GUARDED_BACKUP_STARTED=",
                          "JNS_VM905_BACKUP_VERIFIED="))]
 for line in public:print(line,flush=True)
 if r.returncode:
  if not any(x.startswith("JNS_HA_GENERAL_BACKUP_BLOCKED=") for x in public):
   print("JNS_HA_GENERAL_BACKUP_BLOCKED=remote_failed",flush=True)
  return 1
 if len([x for x in public if x.startswith("JNS_VM905_BACKUP_VERIFIED=")])!=1:
  print("JNS_HA_GENERAL_BACKUP_BLOCKED=verification_missing",flush=True)
  return 1
 print("JNS_HA_GENERAL_BACKUP_WORKFLOW_COMPLETED=yes",flush=True)
 return 0
if __name__=="__main__":
 sys.exit(main())
