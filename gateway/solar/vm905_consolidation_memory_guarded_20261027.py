#!/usr/bin/env python3
"""Guarded VM905 memory uplift (no guest restart), through Node C runner.
Default audit only. --apply requires explicit request file in repository.
Fails closed on VM/backup mismatch, low headroom, or failed integrity checks.
Never prints private Proxmox config, backup paths, addresses, secrets or logs.
"""
import base64,json,os,shlex,subprocess,sys

REMOTE=r'''
import hashlib,json,os,re,subprocess,sys,time
from pathlib import Path
mode=sys.argv[1]
backup=Path("/mnt/pve/NAS/dump/jns-ha-general-consolidation-20261027-v1")
def fail(code):
 print("JNS_VM905_RAM_BLOCKED="+code,flush=True)
 raise SystemExit(77)
def run(argv,timeout=20):
 try:return subprocess.run(argv,capture_output=True,text=True,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):return None
def vmstate():
 p=run(["qm","status","905"])
 return p.stdout.strip() if p and p.returncode==0 else ""
def conf():
 p=run(["qm","config","905"])
 if not p or p.returncode:fail("qm_config_unavailable")
 return p.stdout
def field(cfg,key):
 m=re.search(r"^"+re.escape(key)+r":\s*(.+)$",cfg,re.M)
 return m.group(1).strip() if m else None
def available():
 p=run(["free","-m"])
 if not p or p.returncode:fail("host_ram_unavailable")
 try:return next(int(s.split()[6]) for s in p.stdout.splitlines() if s.startswith("Mem:"))
 except (ValueError,StopIteration,IndexError):fail("host_ram_parse_failed")
def backup_ok():
 m=run(["findmnt","-n","-M","/mnt/pve/NAS","-o","FSTYPE"])
 if not m or m.returncode:fail("archive_storage_not_mounted")
 manifest=backup/"MANIFEST.json"
 if not manifest.is_file() or manifest.is_symlink():fail("no_905_safety_manifest")
 try:j=json.loads(manifest.read_text())
 except (OSError,ValueError):fail("invalid_905_manifest")
 name=j.get("archive_name","")
 if j.get("vm")!=905 or j.get("source_host")!="nodeb" or not re.fullmatch(r"vzdump-qemu-905-[0-9_-]+\.vma\.zst",name):
  fail("wrong_backup_identity")
 p=backup/name
 if not p.is_file() or p.is_symlink() or p.stat().st_size!=j.get("size_bytes",0):fail("backup_size_mismatch")
 if not j.get("zstd_test_passed"):fail("backup_integrity_not_confirmed")
 if time.time()-manifest.stat().st_mtime>48*3600:fail("backup_too_old")
 if mode=="apply":
  h=hashlib.sha256()
  with p.open("rb") as source:
   for block in iter(lambda:source.read(4*1024*1024),b""):h.update(block)
  if h.hexdigest()!=j.get("archive_sha256"):fail("backup_sha256_mismatch")
 return True
if mode not in ("inspect","apply"):fail("wrong_mode")
if os.uname().nodename.split(".")[0]!="nodeb" or os.geteuid()!=0:fail("wrong_host_or_privilege")
cfg=conf()
if field(cfg,"name")!="ha-s2-general" or field(cfg,"memory") not in ("1024","2048"):
 fail("wrong_or_unexpected_vm905")
if field(cfg,"scsi0") is None or not field(cfg,"scsi0").startswith("vmdata:vm-905-disk-1,"):fail("wrong_vm905_disk")
if field(cfg,"lock"):fail("vm_locked")
if vmstate()!="status: running":fail("vm_not_running")
old_mem=field(cfg,"memory")
old_balloon=field(cfg,"balloon")
avail=available()
if mode=="inspect":
 print("JNS_VM905_RAM_PREFLIGHT="+json.dumps({"vm905_running":True,"current_memory_mib":int(old_mem),
 "balloon_mib":int(old_balloon) if old_balloon and old_balloon.isdecimal() else None,
 "host_available_mib":avail,"backup_manifest_verified":backup_ok(),"mode":"read_only"},sort_keys=True),flush=True)
 raise SystemExit(0)
if not backup_ok():fail("backup_unverified")
if avail<2400:fail("not_enough_host_ram")
if old_mem=="2048" and old_balloon=="0":
 print("JNS_VM905_RAM_APPLY="+json.dumps({"already_set":True,"memory_mib":2048,"balloon_mib":0},sort_keys=True),flush=True)
 raise SystemExit(0)
if old_mem!="1024" or old_balloon!="768":fail("unexpected_original_memory_or_balloon")
# This alters only persistent Proxmox VM RAM configuration.
# It does not reboot, stop, resume, reset, migrate or hotplug guest devices.
p=run(["qm","set","905","--memory","2048","--balloon","0"],35)
if not p or p.returncode:
 print("JNS_VM905_RAM_APPLY_FAILED=qm_set",flush=True)
 raise SystemExit(78)
new=conf()
new_mem=field(new,"memory");new_balloon=field(new,"balloon")
healthy=(new_mem=="2048" and new_balloon=="0" and vmstate()=="status: running")
if not healthy:
 rb=run(["qm","set","905","--memory","1024","--balloon","768"],35)
 print("JNS_VM905_RAM_ROLLBACK="+json.dumps({"attempted":True,"command_ok":bool(rb and rb.returncode==0)}),flush=True)
 fail("post_apply_verification_failed")
print("JNS_VM905_RAM_APPLY="+json.dumps({"memory_mib":2048,"balloon_mib":0,
 "vm_still_running":True,"reboot_performed":False,
 "host_available_mib_after":available(),"guest_memory_effective_requires_runtime_check":True},sort_keys=True),flush=True)
'''
def main():
 mode="apply" if "--apply" in sys.argv[1:] else "inspect"
 if os.uname().nodename.split(".")[0]!="nodec":
  print("JNS_VM905_RAM_BLOCKED=wrong_runner",flush=True);return 1
 if mode=="apply" and not os.path.isfile("gateway/solar/requests/vm905-memory-20261027.request"):
  print("JNS_VM905_RAM_BLOCKED=no_explicit_request",flush=True);return 1
 b=base64.b64encode(REMOTE.encode()).decode()
 argv=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes",
       "-o","ConnectTimeout=6","nodeb",shlex.join(["python3","-u","-c",
       "exec(__import__('base64').b64decode('"+b+"'))",mode])]
 try:r=subprocess.run(argv,capture_output=True,text=True,timeout=520 if mode=="apply" else 55)
 except (OSError,subprocess.TimeoutExpired):
  print("JNS_VM905_RAM_BLOCKED=transport_failure",flush=True);return 1
 for line in r.stdout.splitlines():
  if line.startswith(("JNS_VM905_RAM_",)):print(line,flush=True)
 if r.returncode:
  if not "JNS_VM905_RAM_BLOCKED=" in r.stdout and not "JNS_VM905_RAM_APPLY_FAILED=" in r.stdout:
   print("JNS_VM905_RAM_BLOCKED=remote_command_failure",flush=True)
  return 1
 return 0
if __name__=="__main__":sys.exit(main())
