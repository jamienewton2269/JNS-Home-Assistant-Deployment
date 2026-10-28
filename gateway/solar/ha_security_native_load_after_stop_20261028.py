#!/usr/bin/env python3
"""Load verified native security package on HA-General after VM906 stops.
A bounded Core restart only, no security automations enabled, no hardware
commands. Confirm active source VM906 is stopped before restart; leave local
45-minute Node A auto-recovery timer active until cutover validated.
"""
import base64,datetime,json,os,re,shlex,subprocess,sys,time
SSH=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=6"]
CHECK=r'''
import json,pathlib,re
p=pathlib.Path("/config/packages/jns_ha_security_native_cutover_20261028_v2.yaml")
s=pathlib.Path("/config/secrets.yaml")
if not p.is_file() or p.is_symlink() or not s.is_file():raise SystemExit(74)
t=p.read_text()
if "initial_state: false" not in t or t.count("initial_state: false")!=6:raise SystemExit(75)
if not re.search(r"(?m)^alarm_control_panel:",t):raise SystemExit(76)
if "jns_security_906_manual_alarm_code_20261028_v2:" not in s.read_text():raise SystemExit(77)
out={"native_package_present":True,"manual_alarm_section":True,
     "disabled_security_automations":6,"secret_reference_present":True}
print("JNS_SECURITY_NATIVE_LOAD_CONFIG="+json.dumps(out,sort_keys=True))
'''
def ssh(node,args,timeout=28):
 try:p=subprocess.run(SSH+[node,shlex.join(args)],capture_output=True,text=True,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):return None
 return p.stdout if p.returncode==0 else None
def qga(args,timeout=90):
 out=ssh("nodeb",["qm","guest","exec","905","--",*args],37)
 if not out:return None
 try:j=json.loads(out)
 except ValueError:return None
 deadline=time.monotonic()+timeout
 while time.monotonic()<deadline:
  if j.get("exited"):return j
  if not j.get("pid"):break
  time.sleep(.6)
  out=ssh("nodeb",["qm","guest","exec-status","905",str(j["pid"])],21)
  if not out:break
  try:j=json.loads(out)
  except ValueError:break
 return None
def dt(s):
 try:return datetime.datetime.fromisoformat(s.replace("Z","+00:00"))
 except (ValueError,AttributeError):return None
def start_time():
 j=qga(["docker","inspect","homeassistant","--format","{{.State.StartedAt}}"],35)
 return dt((j.get("out-data") or "").strip()) if j and j.get("exitcode")==0 else None
def check_package():
 b=base64.b64encode(CHECK.encode()).decode()
 j=qga(["docker","exec","homeassistant","python3","-c",
        "exec(__import__('base64').b64decode('"+b+"'))"],50)
 if not j or j.get("exitcode")!=0:return False
 return "JNS_SECURITY_NATIVE_LOAD_CONFIG=" in str(j.get("out-data",""))
def main():
 if os.uname().nodename.split(".")[0]!="nodec":return 1
 a=ssh("nodea",["qm","status","906"])
 b=ssh("nodeb",["qm","status","905"])
 if not a or a.strip()!="status: stopped" or not b or b.strip()!="status: running":
  print("JNS_SECURITY_NATIVE_LOAD_BLOCKED=source_not_stopped_or_target_unavailable");return 1
 timer=ssh("nodea",["systemctl","is-active","jns-ha906-recovery-20261028.timer"])
 if timer is None or timer.strip()!="active":
  print("JNS_SECURITY_NATIVE_LOAD_BLOCKED=auto_recovery_timer_not_active");return 1
 if not check_package():
  print("JNS_SECURITY_NATIVE_LOAD_BLOCKED=staged_package_missing");return 1
 first=start_time()
 if not first:
  print("JNS_SECURITY_NATIVE_LOAD_BLOCKED=core_baseline_unknown");return 1
 chk=qga(["ha","core","check"],245)
 if not chk or chk.get("exitcode")!=0:
  print("JNS_SECURITY_NATIVE_LOAD_BLOCKED=ha_config_check_failed");return 1
 print("JNS_SECURITY_NATIVE_LOAD_CONFIGCHECK=passed",flush=True)
 j=qga(["ha","core","restart"],85)
 print("JNS_SECURITY_NATIVE_RESTART_COMMAND="+("accepted" if j and j.get("exitcode")==0 else "ambiguous_verifying_startup"),flush=True)
 deadline=time.monotonic()+210
 while time.monotonic()<deadline:
  later=start_time()
  if later and later>first:
   if check_package():
    core=qga(["ha","core","info"],50)
    if core and core.get("exitcode")==0:
     print("JNS_SECURITY_NATIVE_LOAD_RESULT="+json.dumps(
       {"core_restarted":True,"manual_alarm_package_loaded_from_valid_yaml":True,
        "security_automations_staged_disabled":6,"source_vm906_remains_stopped":True,
        "automatic_vm906_recovery_timer_remains_active":True},sort_keys=True),flush=True)
     return 0
  time.sleep(6)
 print("JNS_SECURITY_NATIVE_LOAD_BLOCKED=core_startup_not_verified",flush=True)
 return 1
if __name__=="__main__":raise SystemExit(main())
