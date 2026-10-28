#!/usr/bin/env python3
"""One-time guarded VM906 stop after graceful shutdown failed in approved window.
Requires local 45m timed recovery and VM905 running. No override of locks.
"""
import base64,os,subprocess,shlex,sys
SSH=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=6"]
SOURCE=r'''
import json,os,re,subprocess
def run(args,timeout=35):
 try:return subprocess.run(args,capture_output=True,text=True,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):return None
def fail(reason):
 print("JNS_VM906_FORCE_STOP_BLOCKED="+reason,flush=True);raise SystemExit(71)
if os.geteuid()!=0 or os.uname().nodename.split(".")[0]!="nodea":fail("identity")
t=run(["systemctl","is-active","jns-ha906-recovery-20261028.timer"])
if not t or t.returncode or t.stdout.strip()!="active":fail("recovery_timer_inactive")
c=run(["qm","config","906"]);q=run(["qm","status","906"])
if not c or c.returncode or not re.search(r"^name:\s*ha-security\s*$",c.stdout,re.M):fail("vm_identity")
if re.search(r"^lock:",c.stdout,re.M):fail("locked")
if not q or q.returncode:fail("status_unknown")
if q.stdout.strip()=="status: stopped":
 print("JNS_VM906_CUTOVER_ISOLATION=already_stopped_with_auto_recovery",flush=True)
 raise SystemExit(0)
if q.stdout.strip()!="status: running":fail("unexpected_state")
r=run(["qm","stop","906","--timeout","35"],55)
q=run(["qm","status","906"],15)
if not q or q.returncode or q.stdout.strip()!="status: stopped":
 fail("force_stop_unverified")
print("JNS_VM906_CUTOVER_ISOLATION=stopped_timer_active",flush=True)
'''
def main():
 if os.uname().nodename.split(".")[0]!="nodec":return 1
 target=subprocess.run(SSH+["nodeb",shlex.join(["qm","status","905"])],
                      capture_output=True,text=True,timeout=22)
 if target.returncode or target.stdout.strip()!="status: running":
  print("JNS_VM906_FORCE_STOP_BLOCKED=target_ha_general_not_running");return 1
 b=base64.b64encode(SOURCE.encode()).decode()
 r=subprocess.run(SSH+["nodea",shlex.join(["python3","-u","-c",
                   "exec(__import__('base64').b64decode('"+b+"'))"])],
                  capture_output=True,text=True,timeout=85)
 for l in r.stdout.splitlines():
  if l.startswith(("JNS_VM906_FORCE_STOP_BLOCKED=","JNS_VM906_CUTOVER_ISOLATION=")):
   print(l,flush=True)
 return 0 if r.returncode==0 and "JNS_VM906_CUTOVER_ISOLATION=" in r.stdout else 1
if __name__=="__main__":sys.exit(main())
