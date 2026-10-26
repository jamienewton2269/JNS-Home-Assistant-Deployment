#!/usr/bin/env python3
"""Guarded Plant Manager archival. Preserve VM903 before any planned cold shutdown.

Node C runner -> established authorised SSH to Node B. No deletions, no HA
configuration/recorder edits, no Node C VM creation, no force-stop. Two verified
archives on off-host NAS: live safety copy, followed by cold-state backup.
"""
import base64,subprocess,shlex,sys
REMOTE=r'''
import hashlib,json,os,re,subprocess,sys,time
from pathlib import Path
def fail(code):
 print("JNS_PLANT_COLD_ARCHIVE_BLOCKED="+code,flush=True);sys.exit(1)
def r(argv,secs=25):
 try:return subprocess.run(argv,capture_output=True,text=True,timeout=secs)
 except (OSError,subprocess.TimeoutExpired):return None
if os.geteuid()!=0 or os.uname().nodename.split(".")[0]!="nodeb":fail("not_authorised_nodeb_root")
c=r(["qm","config","903"])
q=r(["qm","status","903"])
if not c or c.returncode or not q or q.returncode:fail("source_unavailable")
if not re.search(r"^name:\s+ha-s1-plant\s*$",c.stdout,re.M):fail("incorrect_guest_name")
if not re.search(r"^onboot:\s*1\s*$",c.stdout,re.M):fail("unexpected_onboot")
if q.stdout.strip()!="status: running":fail("plant_already_stopped_or_changed_reaudit")
if re.search(r"^lock:",c.stdout,re.M):fail("source_locked")
if not re.search(r"^agent:\s*(?:enabled=)?1(?:,|$)",c.stdout,re.M):fail("qga_missing")
if not re.search(r"^scsi0:\s*vmdata:vm-903-disk-1,",c.stdout,re.M):fail("unexpected_primary_disk")
if not re.search(r"^efidisk0:\s*vmdata:vm-903-disk-0,",c.stdout,re.M):fail("unexpected_efi_disk")
if re.search(r"^(?:hostpci|usb|virtiofs|hookscript)\d*:",c.stdout,re.M):fail("unexpected_passthrough")
p=r(["qm","agent","903","ping"],10)
if not p or p.returncode:fail("guest_agent_not_healthy")
nas=Path("/mnt/pve/NAS")
dest=nas/"dump"
f=r(["findmnt","-n","-M",str(nas)],9)
if not f or f.returncode:fail("nas_mount_inactive")
if not dest.is_dir() or dest.is_symlink():fail("nas_dump_dir_unavailable")
p=r(["pvesm","status"],12)
if not p or p.returncode or not any(re.match(r"^NAS\s+cifs\s+active\b",l) for l in p.stdout.splitlines()):
 fail("nas_storage_not_ready")
p=r(["df","-Pk",str(dest)])
if not p or p.returncode:fail("nas_capacity_unavailable")
try:available_kib=int(p.stdout.splitlines()[-1].split()[3])
except (IndexError,ValueError):fail("nas_capacity_bad")
if available_kib < 75*1048576:fail("nas_below_75g_safety_threshold")
# Guest disk size known as 32 GiB; hard fail on unexpected sizing rather than fill NAS.
m=re.search(r"^scsi0:.*\bsize=(\d+)G(?:,|$)",c.stdout,re.M)
if not m or int(m.group(1))>35:fail("disk_size_not_confirmed")
old={p.name for p in dest.iterdir() if p.is_file() and p.name.startswith("vzdump-qemu-903-") and p.name.endswith(".vma.zst")}
if old:fail("existing_archive_present_manual_review")
def backup_and_verify(stage,mode):
 before={p.name for p in dest.iterdir() if p.is_file() and p.name.startswith("vzdump-qemu-903-") and p.name.endswith(".vma.zst")}
 job=r(["vzdump","903","--mode",mode,"--compress","zstd","--dumpdir",str(dest)],2100)
 if not job or job.returncode:fail(stage+"_vzdump_failed")
 after=[p for p in dest.iterdir() if p.is_file() and p.name.startswith("vzdump-qemu-903-") and p.name.endswith(".vma.zst") and p.name not in before]
 if len(after)!=1:fail(stage+"_archive_count_not_one")
 path=after[0]
 size=path.stat().st_size
 if size<100*1024*1024:fail(stage+"_archive_too_small")
 test=r(["zstd","-t",str(path)],780)
 if not test or test.returncode:fail(stage+"_zstd_integrity_failed")
 sha=hashlib.sha256()
 with path.open("rb") as f:
  for block in iter(lambda:f.read(4*1024*1024),b""):sha.update(block)
 print("JNS_PLANT_"+stage+"_ARCHIVE_VERIFIED="+json.dumps({"bytes":size,"sha256":sha.hexdigest(),"zstd_test_ok":True},sort_keys=True),flush=True)
 return {"file":path.name,"bytes":size,"sha256":sha.hexdigest(),"stage":stage}
print("JNS_PLANT_PRE_ARCHIVE_SOURCE=running; backups_location=NAS; DB_edits=no",flush=True)
live=backup_and_verify("SAFETY_LIVE","snapshot")
q=r(["qm","status","903"])
if not q or q.returncode or q.stdout.strip()!="status: running":fail("source_changed_after_safety_copy")
# Graceful shutdown only. No qm stop, no kill, no force-stop.
down=r(["qm","shutdown","903","--timeout","180"],240)
q=r(["qm","status","903"])
if not down or down.returncode or not q or q.returncode or q.stdout.strip()!="status: stopped":
 fail("graceful_shutdown_not_confirmed_live_backup_preserved")
print("JNS_PLANT_GRACEFUL_SHUTDOWN_VERIFIED=yes",flush=True)
off=r(["qm","set","903","--onboot","0"],20)
if not off or off.returncode:fail("disable_onboot_failed_guest_stopped")
c2=r(["qm","config","903"])
if not c2 or c2.returncode or not re.search(r"^onboot:\s*0\s*$",c2.stdout,re.M):fail("onboot_disabled_not_confirmed")
# Ensure backup timestamps do not collide at second precision.
time.sleep(2)
cold=backup_and_verify("COLD","stop")
q=r(["qm","status","903"])
if not q or q.returncode or q.stdout.strip()!="status: stopped":fail("cold_backup_unexpected_guest_state")
manifest=dest/"jns-plant-manager-vm903-cold-20261026.json"
data={"vmid":903,"role":"ha-s1-plant","created_utc":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),
      "source_status":"stopped","onboot":0,"backups":[live,cold],"recorder_preserved":True,
      "guest_db_modifications":False,"restore_tested":False}
try:
 with manifest.open("x",encoding="utf-8") as f:
  json.dump(data,f,sort_keys=True,indent=2);f.write("\n")
except FileExistsError:fail("manifest_already_exists_archives_retained")
try:os.chmod(manifest,0o600)
except OSError:pass
print("JNS_PLANT_COLD_ARCHIVE_COMPLETE="+json.dumps({
 "source_node":"nodeb","source_guest_stopped":True,"onboot_disabled":True,
 "offhost_backup_files":2,"sha256_and_zstd_verified":True,"manifest_created":True,
 "proxmox_guest_definition_preserved":True,"nodec_restore_tested":False,"db_modified":False},sort_keys=True),flush=True)
'''
def main():
    encoded=base64.b64encode(REMOTE.encode()).decode()
    cmd=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=6",
         "nodeb",shlex.join(["python3","-u","-c","exec(__import__('base64').b64decode('"+encoded+"'))"])]
    try:p=subprocess.run(cmd,capture_output=True,text=True,timeout=3000)
    except (OSError,subprocess.TimeoutExpired):
        print("JNS_PLANT_COLD_ARCHIVE_GATEWAY_TIMEOUT");raise SystemExit(1)
    for line in p.stdout.splitlines():
        if line.startswith(("JNS_PLANT_","JNS_PLANT_COLD_ARCHIVE_BLOCKED=")):
            print(line,flush=True)
    if p.returncode:raise SystemExit(p.returncode)
if __name__=="__main__":main()
