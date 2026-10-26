#!/usr/bin/env python3
"""JNS HA-Security VM906 cold-start to enable QGA (ONE guarded restart).

Only after successful native Proxmox off-host backup and fresh gates.
Never performs qm stop/reset, database operations, DNS/IP changes or VM restore.
If shutdown fails, leave live guest untouched; if starting fails, do not
start a second copy elsewhere.
"""
import base64,subprocess,json,shlex,sys
SSH=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=6"]
def abort(code):
 print("JNS_VM906_AGENT_COLDSTART_BLOCKED="+code,flush=True);raise SystemExit(1)
def remote(host,code,timeout):
 encoded=base64.b64encode(code.encode()).decode()
 argv=SSH+[host,shlex.join(["python3","-u","-c","exec(__import__('base64').b64decode('"+encoded+"'))"])]
 try:r=subprocess.run(argv,capture_output=True,text=True,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):abort(host+"_timeout")
 for l in r.stdout.splitlines():
  if l.startswith(("JNS_VM906_","JNS_BACKUP_")):print(l,flush=True)
 if r.returncode:abort(host+"_failed_rc_"+str(r.returncode))
 return r.stdout
VERIFY=r'''
import json,os,hashlib,sys,re,time
from pathlib import Path
p=Path("/mnt/pve/NAS/dump/jns-vm906-agent-recovery-20261026-v1")
if os.geteuid()!=0 or os.uname().nodename.split(".")[0]!="nodeb":sys.exit(70)
m=p/"MANIFEST.json"
if not m.is_file() or m.is_symlink():sys.exit(71)
a=json.loads(m.read_text())
if not a.get("snapshot_read_only_guest") or a.get("source_node")!="nodea":sys.exit(72)
if not re.fullmatch(r"vzdump-qemu-906-[0-9_-]+\.vma\.zst",a.get("name","")):sys.exit(73)
file=p/a["name"]
if not file.is_file() or file.is_symlink() or file.stat().st_size!=a.get("size"):sys.exit(74)
if file.stat().st_mtime < time.time()-48*3600:sys.exit(75)
h=hashlib.sha256()
with file.open("rb") as f:
 for b in iter(lambda:f.read(4*1024*1024),b""):h.update(b)
if h.hexdigest()!=a.get("sha256"):sys.exit(76)
if not (p/"vm906-proxmox.conf").is_file():sys.exit(77)
print("JNS_BACKUP_OFFHOST_RECOVERY_GATE=yes",flush=True)
'''
RESTART=r'''
import os,re,json,time,sys,subprocess,socket,urllib.error,urllib.request
def fail(c):print("JNS_VM906_AGENT_COLDSTART_BLOCKED="+c,flush=True);sys.exit(90)
def run(args,timeout=15):
 try:return subprocess.run(args,capture_output=True,text=True,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):return None
if os.geteuid()!=0 or os.uname().nodename.split(".")[0]!="nodea":fail("wrong_identity")
c=run(["qm","config","906"])
q=run(["qm","status","906"])
if not c or c.returncode or not q or q.returncode or q.stdout.strip()!="status: running":fail("vm_not_running")
if not re.search(r"^name:\s*ha-security\s*$",c.stdout,re.M):fail("wrong_guest")
if not re.search(r"^agent:\s*(?:enabled=)?1(?:,|$)",c.stdout,re.M):fail("agent_not_enabled")
if re.search(r"^lock:",c.stdout,re.M):fail("vm_locked")
if re.search(r"^onboot:\s*1\s*$",c.stdout,re.M):fail("unexpected_autostart")
if re.search(r"^(usb\d+|hostpci\d+|virtiofs\d+|hookscript|args):",c.stdout,re.M):fail("passthrough_review_needed")
p=run(["qm","agent","906","ping"],9)
if p and p.returncode==0:
 print("JNS_VM906_GUEST_AGENT_HEALTHY_ALREADY=yes",flush=True)
 sys.exit(0)
f=run(["free","-m"])
if not f or f.returncode:fail("memory_unavailable")
avail=0
for line in f.stdout.splitlines():
 if line.startswith("Mem:"):avail=int(line.split()[6])
if avail<1300:fail("insufficient_ram")
def tcp80():
 try:
  with socket.create_connection(("ha-security.home.arpa",80),timeout=4):return True
 except OSError:return False
if not tcp80():fail("security_public_endpoint_not_ready_pre")
print("JNS_VM906_COLDSTART_PRECHECKS_OK=yes",flush=True)
# Graceful shutdown only. The shutdown command waits up to 180s.
p=run(["qm","shutdown","906","--timeout","180"],220)
if not p or p.returncode:fail("graceful_shutdown_failed_guest_may_be_running")
q=run(["qm","status","906"],9)
if not q or q.returncode or q.stdout.strip()!="status: stopped":fail("guest_not_stopped_after_graceful_shutdown")
print("JNS_VM906_GRACEFUL_SHUTDOWN_OK=yes",flush=True)
p=run(["qm","start","906"],120)
if not p or p.returncode:
 print("JNS_VM906_START_FAILED_RECOVERY_REQUIRED=yes",flush=True)
 fail("start_failed")
q=run(["qm","status","906"],9)
if not q or q.returncode or q.stdout.strip()!="status: running":fail("post_start_state_unknown")
print("JNS_VM906_BOOTED=yes",flush=True)
agent=False
for i in range(30):
 p=run(["qm","agent","906","ping"],8)
 if p and p.returncode==0:agent=True;break
 time.sleep(5)
public=False
for i in range(30):
 if tcp80():public=True;break
 time.sleep(4)
print("JNS_VM906_POST_COLDSTART="+json.dumps({
 "guest_running":True,"qga_ping":agent,"public_http_tcp_80_reachable":public,
 "guest_core_docker_not_yet_audited":True,"no_database_edits":True,
 "no_forced_stop":True},sort_keys=True),flush=True)
if not agent or not public:fail("postcheck_incomplete_guest_left_running")
'''
def main():
 import os
 if os.uname().nodename.split(".")[0]!="nodec":abort("wrong_runner")
 if "JNS_BACKUP_OFFHOST_RECOVERY_GATE=yes" not in remote("nodeb",VERIFY,420):
  abort("backup_gate_missing")
 remote("nodea",RESTART,660)
 print("JNS_VM906_QGA_ACTIVATION_CONFIRMED=yes",flush=True)
if __name__=="__main__":main()
