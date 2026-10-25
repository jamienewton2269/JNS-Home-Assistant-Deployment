#!/usr/bin/env python3
"""JNS Solar HA900 removal after a verified complete VMA archive on Node C NFS.

THIS IS DESTRUCTIVE and is user-authorised for VM900 ONLY.
Checks protected manifest and backup+config SHA256, stopped/onboot=0,
source config SHA equality before calling qm destroy. Never acts on Node C VM909.
"""
import datetime,hashlib,json,os,pathlib,re,shlex,subprocess,sys
SSH=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=6"]
ARC_DIR=pathlib.Path("/mnt/pve/nfs-ct/JNS-Solar-Archives/HA900-cold-20261025")
def fail(why):
 print("JNS_HA900_DELETE_BLOCKED="+why,flush=True);sys.exit(1)
def hash_file(path):
 h=hashlib.sha256()
 with path.open("rb") as f:
  for part in iter(lambda:f.read(4*1024*1024),b""):h.update(part)
 return h.hexdigest()
def verify_archive():
 if os.uname().nodename.split(".")[0]!="nodec" or os.geteuid()==0:fail("NODEC_RUNNER_IDENTITY")
 if subprocess.run(["findmnt","-rn","-M","/mnt/pve/nfs-ct"],capture_output=True).returncode!=0:
  fail("NFS_NOT_MOUNTED")
 if ARC_DIR.is_symlink() or not ARC_DIR.is_dir():fail("ARCHIVE_DIRECTORY_MISSING")
 if ARC_DIR.stat().st_mode&0o077:fail("ARCHIVE_DIRECTORY_NOT_PRIVATE")
 mf=ARC_DIR/"RESTORE_MANIFEST.json"
 if not mf.is_file() or mf.is_symlink():fail("RESTORE_MANIFEST_MISSING")
 try:m=json.loads(mf.read_text())
 except (OSError,ValueError):fail("RESTORE_MANIFEST_INVALID")
 if (m.get("archive_format")!="Proxmox vzdump-qemu VMA zstd" or m.get("vmid")!=900
     or m.get("source_host")!="nodea" or m.get("destination_host")!="nodec"
     or m.get("state_at_backup")!="stopped" or m.get("source_onboot")!=0
     or m.get("source_vm_deleted") is not False):
  fail("MANIFEST_DOES_NOT_AUTHORISE_DELETION")
 for flag in ("nfs_sha256","zstd_decompress","vma_verify","source_remains_stopped"):
  if m.get("verified",{}).get(flag) is not True:fail("RESTORE_VERIFICATION_MISSING_"+flag)
 name=m.get("vzdump_archive_filename","")
 if not isinstance(name,str) or not re.fullmatch(r"vzdump-qemu-900-[0-9_-]+\.vma\.zst",name):
  fail("UNEXPECTED_BACKUP_FILENAME")
 b=ARC_DIR/name
 if not b.is_file() or b.is_symlink() or b.stat().st_size!=m.get("size_bytes"):
  fail("BACKUP_SIZE_MISMATCH")
 if hash_file(b)!=m.get("sha256"):fail("BACKUP_SHA256_MISMATCH")
 cfg=ARC_DIR/"ha900-original-proxmox.conf"
 if not cfg.is_file() or cfg.is_symlink() or hash_file(cfg)!=m.get("proxmox_config_sha256"):
  fail("VM_CONFIG_BACKUP_MISSING_OR_DAMAGED")
 return m
REMOTE=r'''
import json,hashlib,re,subprocess,sys,os
if os.geteuid()!=0 or os.uname().nodename.split(".")[0]!="nodea":sys.exit(70)
EXPECTED_CONFIG_SHA="__CONFIG_SHA__"
def r(cmd,timeout=65):
 p=subprocess.run(cmd,capture_output=True,text=True,timeout=timeout)
 if p.returncode:raise RuntimeError("operation_exit")
 return p.stdout
assert r(["qm","status","900"]).strip()=="status: stopped"
config=r(["qm","config","900"])
assert hashlib.sha256(config.encode()).hexdigest()==EXPECTED_CONFIG_SHA
assert re.search(r"^name:\s+homeassistant-recovery\s*$",config,re.M)
assert re.search(r"^onboot:\s+0\s*$",config,re.M)
for key,name in (("scsi0","vm-900-disk-1"),("efidisk0","vm-900-disk-0")):
 assert re.search(r"^"+key+r":\s+vmdata:"+name+r"(?:,|\s|$)",config,re.M)
 for _ in (1,):
  assert r(["zfs","list","-Hp","-o","type","vmdata/"+name]).strip()=="volume"
before=int(r(["zfs","list","-Hp","-o","available","vmdata"]).strip())
# VM900 has been explicitly approved for permanent removal after NAS backup.
result=subprocess.run(["qm","destroy","900","--purge","1",
                       "--destroy-unreferenced-disks","1"],
                      capture_output=True,text=True,timeout=180)
if result.returncode!=0:raise RuntimeError("qm_destroy_failed")
# No force-delete of ZFS datasets: if PVE retained them, report that as incomplete.
config_gone=subprocess.run(["qm","config","900"],capture_output=True).returncode!=0
if not config_gone:raise RuntimeError("vm900_config_still_present")
remaining=[]
for name in ("vm-900-disk-0","vm-900-disk-1"):
 if subprocess.run(["zfs","list","-H","vmdata/"+name],
                   stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0:
  remaining.append(name)
stage="vmdata/jns-solar-ha900-vzdump-20261025"
stage_removed=False
if not remaining and subprocess.run(["zfs","list","-H",stage],
        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0:
 stage_result=subprocess.run(["zfs","destroy",stage],capture_output=True,timeout=35)
 stage_removed=stage_result.returncode==0
after=int(r(["zfs","list","-Hp","-o","available","vmdata"]).strip())
out={"vm900_config_removed":config_gone,"vm900_disks_remaining":len(remaining),
     "backup_stage_removed":stage_removed,"vmdata_free_delta_gib":round((after-before)/1073741824,1)}
print("JNS_HA900_RETIREMENT_JSON="+json.dumps(out,sort_keys=True))
'''
def delete_source(config_sha):
 script=REMOTE.replace("__CONFIG_SHA__",config_sha)
 cmd=SSH+["nodea",shlex.join(["python3","-c",script])]
 try:p=subprocess.run(cmd,capture_output=True,text=True,timeout=250)
 except (OSError,subprocess.TimeoutExpired):fail("NODEA_CLEANUP_TIMEOUT")
 if p.returncode:
  print("NODEA_CLEANUP_EXIT="+str(p.returncode),flush=True)
  fail("NODEA_RETIREMENT_FAILED_OR_PARTIAL")
 lines=[x for x in p.stdout.splitlines() if x.startswith("JNS_HA900_RETIREMENT_JSON=")]
 if len(lines)!=1:fail("RETIREMENT_RESULT_MISSING")
 try:d=json.loads(lines[0].split("=",1)[1])
 except ValueError:fail("RETIREMENT_RESULT_INVALID")
 return d
def main():
 print("JNS_HA900_VERIFIED_ARCHIVE_CLEANUP_GATE",flush=True)
 m=verify_archive()
 print("HA900_NFS_ARCHIVE_RECHECK_SHA256_OK=yes",flush=True)
 print("HA900_CONFIG_SAVED_AND_SHA256_OK=yes",flush=True)
 info=delete_source(m["proxmox_config_sha256"])
 if info.get("vm900_config_removed") is not True or info.get("vm900_disks_remaining")!=0:
  fail("SOURCE_DISKS_NOT_RECLAIMED")
 result={"vmid":900,"host":"nodea",
  "proxmox_entry_removed":True,"source_zvols_removed":True,
  "temporary_backup_stage_removed":info.get("backup_stage_removed"),
  "vmdata_free_delta_gib":info.get("vmdata_free_delta_gib"),
  "archive_preserved":True,
  "archive_sha256":m["sha256"],
  "retired_utc":datetime.datetime.now(datetime.timezone.utc).isoformat()}
 p=ARC_DIR/"HA900_RETIREMENT_RESULT.json"
 with p.open("x") as f:json.dump(result,f,indent=2,sort_keys=True);f.write("\n")
 os.chmod(p,0o600)
 print("HA900_PROXMOX_VM_REMOVED=yes",flush=True)
 print("HA900_SOURCE_ZVOLS_REMOVED=yes",flush=True)
 print("HA900_TEMPORARY_STAGE_REMOVED="+str(bool(info.get("backup_stage_removed"))).lower(),flush=True)
 print("HA900_VM_DATA_RECLAIMED_GIB="+str(info.get("vmdata_free_delta_gib")),flush=True)
 print("HA900_NFS_ARCHIVE_PRESERVED=yes",flush=True)
 print("JNS_HA900_RETIREMENT_COMPLETE",flush=True)
if __name__=="__main__":main()
