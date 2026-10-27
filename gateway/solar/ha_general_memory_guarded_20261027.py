#!/usr/bin/env python3
"""JNS HA-General VM905 memory staging; fail closed until both source and
destination recovery archives exist and are independently verified.

No guest shutdown/reboot, no changes to Home Assistant configuration,
automations or services, and no Proxmox cluster operations.
Node C runner -> authorised Node B root SSH -> guarded Proxmox qm set.
Reports configured and running memory distinctly.
"""
import base64, json, os, shlex, subprocess, sys
SSH=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=6"]
REMOTE=r'''
import hashlib,json,os,re,subprocess,sys,time
from pathlib import Path
def die(code):
 print("JNS_VM905_MEMORY_BLOCKED="+code,flush=True)
 raise SystemExit(72)
def run(args,timeout=25):
 try:return subprocess.run(args,capture_output=True,text=True,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):return None
def sha(path):
 h=hashlib.sha256()
 with path.open("rb") as f:
  for chunk in iter(lambda:f.read(4*1024*1024),b""):h.update(chunk)
 return h.hexdigest()
if os.uname().nodename.split(".")[0]!="nodeb" or os.geteuid()!=0:die("wrong_host_or_privilege")
mount=run(["findmnt","-n","-M","/mnt/pve/NAS","-o","FSTYPE"])
if not mount or mount.returncode:die("backup_storage_not_mounted")
root=Path("/mnt/pve/NAS/dump")
def backup_905():
 p=root/"jns-ha-general-consolidation-20261027-v1"
 mf=p/"MANIFEST.json"
 if not mf.is_file() or mf.is_symlink():die("vm905_archive_manifest_missing")
 try:m=json.loads(mf.read_text())
 except (OSError,ValueError):die("vm905_manifest_invalid")
 name=m.get("archive_name","")
 if not re.fullmatch(r"vzdump-qemu-905-[0-9_-]+\.vma\.zst",name):die("vm905_archive_name_invalid")
 a=p/name
 c=p/"vm905-proxmox.conf"
 if not a.is_file() or a.is_symlink() or not c.is_file() or c.is_symlink():die("vm905_archive_or_config_missing")
 if a.stat().st_size!=m.get("size_bytes"):die("vm905_archive_size_mismatch")
 if sha(a)!=m.get("archive_sha256") or sha(c)!=m.get("config_sha256"):die("vm905_archive_hash_mismatch")
 if m.get("zstd_test_passed") is not True:die("vm905_integrity_unverified")
 return a.stat().st_size
def backup_902():
 p=root/"jns-vm902-consolidation-20261027-v1"
 mf=p/"MANIFEST.json"
 if not mf.is_file() or mf.is_symlink():die("vm902_offhost_manifest_missing")
 try:m=json.loads(mf.read_text())
 except (OSError,ValueError):die("vm902_offhost_manifest_invalid")
 name=m.get("name","")
 if not re.fullmatch(r"vzdump-qemu-902-[0-9_-]+\.vma\.zst",name):die("vm902_archive_name_invalid")
 a=p/name;c=p/"vm902-proxmox.conf"
 if not a.is_file() or a.is_symlink() or not c.is_file() or c.is_symlink():die("vm902_offhost_files_missing")
 if a.stat().st_size!=m.get("size"):die("vm902_archive_size_mismatch")
 if sha(a)!=m.get("sha256") or sha(c)!=m.get("config_sha256"):die("vm902_offhost_hash_mismatch")
 return a.stat().st_size
def parse_config():
 c=run(["qm","config","905"])
 if not c or c.returncode:die("vm905_config_unavailable")
 return c.stdout
cfg=parse_config()
if not re.search(r"^name:\s*ha-s2-general\s*$",cfg,re.M):die("vm905_identity_mismatch")
if not re.search(r"^scsi0:\s*vmdata:vm-905-disk-1,",cfg,re.M):die("vm905_storage_unexpected")
if re.search(r"^lock:",cfg,re.M):die("vm905_locked")
q=run(["qm","status","905"])
if not q or q.returncode or q.stdout.strip()!="status: running":die("vm905_not_running")
memory=re.search(r"^memory:\s*(\d+)\s*$",cfg,re.M)
balloon=re.search(r"^balloon:\s*(\d+)\s*$",cfg,re.M)
if not memory or not balloon:die("current_vm_memory_incomplete")
oldmem=int(memory.group(1));oldballoon=int(balloon.group(1))
if oldmem>=2048:
 print("JNS_VM905_MEMORY_ALREADY_AT_LEAST_2G=yes",flush=True)
elif (oldmem,oldballoon)!=(1024,768):
 die("unexpected_existing_memory_settings")
if re.search(r"^pending:",cfg,re.M):die("preexisting_pending_config")
p=run(["free","-m"])
if not p or p.returncode:die("nodeb_ram_unavailable")
try:available=next(int(x.split()[6]) for x in p.stdout.splitlines() if x.startswith("Mem:"))
except (StopIteration,IndexError,ValueError):die("nodeb_ram_parse_failure")
if available<2600:die("nodeb_headroom_insufficient")
g=run(["qm","agent","905","ping"],25)
if not g or g.returncode:die("guest_agent_unresponsive_before_change")
if backup_905()<1024*1024 or backup_902()<1024*1024:die("archive_invalid_size")
print("JNS_VM905_MEMORY_PRECONDITIONS_PASSED=yes",flush=True)
if oldmem<2048:
 change=run(["qm","set","905","--memory","2048","--balloon","0"],45)
 if not change or change.returncode:die("qm_set_rejected_check_private_proxmox_log")
after=parse_config()
m=re.search(r"^memory:\s*(\d+)\s*$",after,re.M)
b=re.search(r"^balloon:\s*(\d+)\s*$",after,re.M)
if not m or int(m.group(1))<2048 or not b or (oldmem<2048 and int(b.group(1))!=0):
 die("new_config_does_not_match_requested")
q=run(["qm","status","905"])
if not q or q.returncode or q.stdout.strip()!="status: running":die("vm905_not_running_after_change")
ag=run(["qm","agent","905","ping"],25)
agent_ok=bool(ag and ag.returncode==0)
now=run(["pvesh","get","/nodes/nodeb/qemu/905/status/current","--output-format","json"],20)
runtime_mib=None
try:
 j=json.loads(now.stdout) if now and now.returncode==0 else {}
 if isinstance(j.get("maxmem"),(int,float)):runtime_mib=round(j["maxmem"]/1048576)
except ValueError:pass
out={"configured_max_mib":int(m.group(1)),"ballooning_disabled":int(b.group(1))==0,
     "guest_running":True,"guest_agent_responded":agent_ok,
     "runtime_max_mib":runtime_mib,
     "runtime_at_least_2gb":bool(runtime_mib and runtime_mib>=2048),
     "guest_rebooted":False,"backup_gates_verified":True,
     "host_mem_available_before_mib":available}
print("JNS_VM905_MEMORY_RESULT="+json.dumps(out,sort_keys=True),flush=True)
if not agent_ok:die("guest_agent_unresponsive_after_change_manual_review")
print("JNS_VM905_MEMORY_CONFIG_JOB_DONE=yes",flush=True)
'''
def main():
 if os.uname().nodename.split(".")[0]!="nodec":
  print("JNS_VM905_MEMORY_BLOCKED=wrong_runner",flush=True);return 1
 b64=base64.b64encode(REMOTE.encode()).decode()
 cmd=SSH+["nodeb",shlex.join(["python3","-u","-c",
      "exec(__import__('base64').b64decode('"+b64+"'))"])]
 try:p=subprocess.run(cmd,capture_output=True,text=True,timeout=1300)
 except (OSError,subprocess.TimeoutExpired):
  print("JNS_VM905_MEMORY_BLOCKED=remote_timeout",flush=True);return 1
 allowed=("JNS_VM905_MEMORY_BLOCKED=","JNS_VM905_MEMORY_ALREADY_CONFIGURED=",
          "JNS_VM905_MEMORY_PRECONDITIONS_PASSED=","JNS_VM905_MEMORY_RESULT=",
          "JNS_VM905_MEMORY_CONFIG_JOB_DONE=")
 printed=[line for line in p.stdout.splitlines() if line.startswith(allowed)]
 for line in printed:print(line,flush=True)
 if p.returncode:
  if not any(line.startswith("JNS_VM905_MEMORY_BLOCKED=") for line in printed):
   print("JNS_VM905_MEMORY_BLOCKED=remote_failed",flush=True)
  return 1
 return 0 if any(x.startswith("JNS_VM905_MEMORY_CONFIG_JOB_DONE=") for x in printed) else 1
if __name__=="__main__":sys.exit(main())
