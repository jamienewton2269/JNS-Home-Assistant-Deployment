#!/usr/bin/env python3
"""Idempotent guarded recovery of the SAME HA-Security VM906 on Node A.
Only starts if completely stopped. Never forces a stop, creates or restores
another VM, deletes any backup, or alters guest config.
"""
import base64,subprocess,shlex,sys
REMOTE=r'''
import os,re,json,sys,time,subprocess,socket
def run(argv,t=20):
 try:return subprocess.run(argv,capture_output=True,text=True,timeout=t)
 except (OSError,subprocess.TimeoutExpired):return None
def fail(s):print("JNS_VM906_RESCUE_BLOCKED="+s,flush=True);raise SystemExit(70)
if os.geteuid()!=0 or os.uname().nodename.split(".")[0]!="nodea":fail("wrong_authorised_host")
c=run(["qm","config","906"]);q=run(["qm","status","906"])
if not c or c.returncode or not q or q.returncode:fail("vm_config_unavailable")
if not re.search(r"^name:\s*ha-security\s*$",c.stdout,re.M):fail("incorrect_guest_name")
if not re.search(r"^agent:\s*(?:enabled=)?1(?:,|$)",c.stdout,re.M):fail("agent_device_not_enabled")
if not re.search(r"^scsi0:\s*vmdata:vm-906-disk-1,",c.stdout,re.M):fail("disk_not_as_expected")
if re.search(r"^lock:",c.stdout,re.M):fail("guest_locked")
state=q.stdout.strip()
if state=="status: running":
 print("JNS_VM906_RESCUE_ALREADY_RUNNING=yes",flush=True)
elif state=="status: stopped":
 print("JNS_VM906_RESCUE_CONFIRMED_STOPPED=yes",flush=True)
 a=run(["qm","start","906"],110)
 if not a or a.returncode:fail("same_guest_start_failed")
 print("JNS_VM906_RESCUE_START_REQUESTED=yes",flush=True)
else:fail("unknown_source_state")
q=run(["qm","status","906"],12)
if not q or q.returncode or q.stdout.strip()!="status: running":fail("post_start_not_running")
agent=False
for _ in range(24):
 a=run(["qm","agent","906","ping"],7)
 if a and a.returncode==0:agent=True;break
 time.sleep(4)
print("JNS_VM906_RESCUE_STATUS="+json.dumps({"running":True,"agent_ping":agent,
 "same_node_a_vm":True,"backup_not_modified":True,"databases_not_modified":True},sort_keys=True),flush=True)
# An unavailable agent warrants diagnostics, but never an additional reboot.
'''
src=base64.b64encode(REMOTE.encode()).decode()
args=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=5",
 "nodea",shlex.join(["python3","-u","-c","exec(__import__('base64').b64decode('"+src+"'))"])]
r=subprocess.run(args,capture_output=True,text=True,timeout=225)
for x in r.stdout.splitlines():
 if x.startswith("JNS_VM906_"):print(x,flush=True)
if r.returncode:raise SystemExit(1)
