#!/usr/bin/env python3
"""Guarded stop VM906 ONLY after VM905 has validated inert alarm package.
Schedule time-limited autonomous restoration as a local Node A systemd timer.
Never shutdown VM905. No device commands. No automatic permanent security
handover: fallback returns VM906 if cutover completion marker not present.
"""
import base64,json,os,re,shlex,subprocess,sys,time
SSH=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=6"]
CHECK=r'''
import pathlib,re
p=pathlib.Path("/config/packages/jns_ha_security_native_cutover_20261028_v2.yaml")
if not p.is_file() or p.is_symlink():raise SystemExit(75)
txt=p.read_text()
if txt.count("initial_state: false")!=6 or not re.search(r"(?m)^alarm_control_panel:",txt):
 raise SystemExit(76)
print("JNS_VM905_NATIVE_PACKAGE_READY=yes")
'''
STOP=r'''
import os,re,subprocess,sys
from pathlib import Path
def fail(s):
 print("JNS_VM906_STOP_BLOCKED="+s,flush=True)
 raise SystemExit(71)
if os.geteuid()!=0 or os.uname().nodename.split(".")[0]!="nodea":fail("wrong_host")
def run(args,timeout=75):
 try:return subprocess.run(args,capture_output=True,text=True,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):return None
q=run(["qm","status","906"],12); c=run(["qm","config","906"],12)
if not q or q.returncode or q.stdout.strip()!="status: running":fail("source_not_running")
if not c or c.returncode or not re.search(r"^name:\s*ha-security\s*$",c.stdout,re.M):fail("source_vm_identity")
if re.search(r"^lock:",c.stdout,re.M):fail("vm906_locked")
root=Path("/var/lib/jns-solar/consolidation")
root.mkdir(parents=True,exist_ok=True,mode=0o700)
marker=root/"vm906-handover-complete-20261028"
fenced=root/"vm905-fenced-for-906-recovery-20261028"
if marker.exists() or marker.is_symlink():fail("handover_marker_preexists")
if fenced.exists() or fenced.is_symlink():fail("stale_fencing_attestation")
unit="jns-ha906-recovery-20261028"
timer=run(["systemd-run","--unit",unit,"--on-active=45m","--timer-property=AccuracySec=15s",
           "/bin/bash","-c",
           "if ! test -e /var/lib/jns-solar/consolidation/vm906-handover-complete-20261028 && test -f /var/lib/jns-solar/consolidation/vm905-fenced-for-906-recovery-20261028; then /usr/sbin/qm start 906; else /usr/bin/logger -t jns-906-failback 'SOURCE RESTORE BLOCKED: target fencing not attested; avoid duplicate security controllers'; fi"],22)
if not timer or timer.returncode:fail("automatic_recovery_timer_unavailable")
active=run(["systemctl","is-active",unit+".timer"],16)
if not active or active.returncode or active.stdout.strip()!="active":fail("recovery_timer_not_active")
print("JNS_VM906_FALLBACK_SCHEDULED=45_minutes",flush=True)
stop=run(["qm","shutdown","906","--timeout","80"],100)
q=run(["qm","status","906"],15)
if not q or q.returncode or q.stdout.strip()!="status: stopped":
 fail("graceful_shutdown_unverified")
print("JNS_VM906_STOP_VERIFIED="+
      '{"vm":906,"state":"stopped","automatic_recovery_after_minutes":45,"current_primary_unchanged":true}',flush=True)
'''
def ssh(host,args,timeout=38):
 try:p=subprocess.run(SSH+[host,shlex.join(args)],capture_output=True,text=True,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):return None
 return p.stdout if p.returncode==0 else None
def guest(args,long_core_check=False):
 # HAOS Core validation takes around 30s and can exceed the default QGA
 # execution deadline. The long-running check MUST carry its own explicit
 # guest-exec timeout, with a longer SSH envelope and polling budget.
 cmd=["qm","guest","exec","905"]
 if long_core_check:cmd+=["--timeout","180"]
 cmd+=["--",*args]
 r=ssh("nodeb",cmd,210 if long_core_check else 40)
 if not r:return None
 try:j=json.loads(r)
 except ValueError:return None
 for _ in range(280 if long_core_check else 110):
  if j.get("exited"):return j
  if not j.get("pid"):break
  time.sleep(.7)
  r=ssh("nodeb",["qm","guest","exec-status","905",str(j["pid"])],20)
  if not r:break
  try:j=json.loads(r)
  except ValueError:break
 return None
def main():
 if os.uname().nodename.split(".")[0]!="nodec":
  print("JNS_VM906_STOP_BLOCKED=runner_identity");return 1
 if len(sys.argv)>2 or (len(sys.argv)==2 and sys.argv[1]!="--preflight"):
  print("JNS_VM906_STOP_BLOCKED=unsupported_argument");return 1
 for host,vm,name in (("nodea",906,"ha-security"),("nodeb",905,"ha-s2-general")):
  state=ssh(host,["qm","status",str(vm)])
  cfg=ssh(host,["qm","config",str(vm)]) or ""
  if not state or state.strip()!="status: running" or not re.search("^name: "+name+"$",cfg,re.M):
   print("JNS_VM906_STOP_BLOCKED=source_or_target_state_unexpected");return 1
 tag=base64.b64encode(CHECK.encode()).decode()
 j=guest(["docker","exec","homeassistant","python3","-c",
      "exec(__import__('base64').b64decode('"+tag+"'))"])
 if not j or j.get("exitcode")!=0 or "JNS_VM905_NATIVE_PACKAGE_READY=yes" not in str(j.get("out-data","")):
  print("JNS_VM906_STOP_BLOCKED=native_alarm_package_not_staged");return 1
 # Supervisor store metadata does not prove the privileged one-shot app
 # is INSTALLED. Require membership of the actual installed-app inventory.
 inv=guest(["ha","apps","list","--no-progress","--raw-json"])
 raw={}
 try:
  raw=json.loads(inv.get("out-data") or "{}") if inv and inv.get("exitcode")==0 else {}
  catalog=raw.get("data",{})
  apps=(catalog.get("apps",catalog.get("addons")) if isinstance(catalog,dict) else catalog)
  found=[a for a in apps if isinstance(a,dict) and
         a.get("slug")=="local_jns_ha905_security_handover" and
         a.get("installed") is not False] if isinstance(apps,list) else []
 except (ValueError,TypeError,AttributeError):
  found=[]
 if raw.get("result")!="ok" or len(found)!=1:
  print("JNS_VM906_STOP_BLOCKED=temporary_native_flow_app_not_confirmed_installed");return 1
 print("JNS_VM905_HANDOVER_APP_INSTALLED_INVENTORY=yes",flush=True)
 core_started=time.monotonic()
 chk=guest(["ha","core","check"],long_core_check=True)
 if not chk:
  print("JNS_VM906_STOP_BLOCKED=ha_general_core_check_transport_or_timeout");return 1
 if chk.get("exitcode")!=0:
  print("JNS_VM906_STOP_BLOCKED=ha_general_core_check_failed_exit_"+str(chk.get("exitcode","unknown")));return 1
 print("JNS_VM905_CORE_CHECK_VERIFIED=passed_elapsed_seconds_"+str(round(time.monotonic()-core_started,1)),flush=True)
 print("JNS_VM906_STOP_PREFLIGHT=passed",flush=True)
 # The Node C recovery cron MUST be installed and attested before isolation.
 # Both repository code and staged runner-owned file must be identical.
 import pathlib,hashlib
 local=pathlib.Path(__file__).parent/"ha906_nodec_auto_failback_20261028.py"
 staged=pathlib.Path.home()/".local/share/jns-security-failback-20261028/auto_failback.py"
 if not local.is_file() or not staged.is_file() or local.read_bytes()!=staged.read_bytes():
  print("JNS_VM906_STOP_BLOCKED=nodec_failback_source_not_staged_exactly");return 1
 if len(sys.argv)==2 and sys.argv[1]=="--preflight":
  print("JNS_VM906_PREFLIGHT_ONLY=ready_no_vm_changes_no_timer_armed",flush=True)
  return 0
 try:arm=subprocess.run(["python3",str(staged),"--arm"],capture_output=True,text=True,timeout=95)
 except (OSError,subprocess.TimeoutExpired):arm=None
 if not arm or arm.returncode or "JNS_HA906_SAFE_AUTO_FAILBACK_ARMED=" not in arm.stdout:
  print("JNS_VM906_STOP_BLOCKED=nodec_fallback_not_armed");return 1
 print("JNS_VM906_FAILBACK_INTERLOCK=NodeC_35m_and_NodeA_fence_gated_45m",flush=True)
 b=base64.b64encode(STOP.encode()).decode()
 try:p=subprocess.run(SSH+["nodea",shlex.join(["python3","-u","-c",
           "exec(__import__('base64').b64decode('"+b+"'))"])],
           capture_output=True,text=True,timeout=145)
 except (OSError,subprocess.TimeoutExpired):
  print("JNS_VM906_STOP_BLOCKED=nodea_transport_or_timeout");return 1
 for line in p.stdout.splitlines():
  if line.startswith(("JNS_VM906_STOP_BLOCKED=","JNS_VM906_FALLBACK_SCHEDULED=","JNS_VM906_STOP_VERIFIED=")):
   print(line,flush=True)
 return 0 if p.returncode==0 and "JNS_VM906_STOP_VERIFIED=" in p.stdout else 1
if __name__=="__main__":sys.exit(main())
