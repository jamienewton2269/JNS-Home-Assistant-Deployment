#!/usr/bin/env python3
"""Reset expected-error one-shot app to a genuinely installed STOPPED state.

Only the temporary app is uninstalled; no HA Core restarts, no VM power,
no secret use, no config-flow. After uninstall, separately runs vetted
install-stopped script and independently proves installed inventory.
"""
import base64,json,os,pathlib,shlex,subprocess,sys,time
ROOT=pathlib.Path(__file__).parent
SSH=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=6"]
APP="local_jns_ha905_security_handover"
SECRET="/mnt/data/supervisor/share/jns-security-handover-20261028/enrolment.json"
def note(k,v):print("JNS_ESPHOME_APP_SAFE_RESET_"+k+"="+str(v),flush=True)
def ssh(n,cmd,limit=34):
 try:return subprocess.run(SSH+[n,shlex.join(cmd)],capture_output=True,text=True,timeout=limit)
 except (OSError,subprocess.TimeoutExpired):return None
def qga(args,limit=100):
 p=ssh("nodeb",["qm","guest","exec","905","--",*args],37)
 if not p or p.returncode:return None
 try:j=json.loads(p.stdout)
 except (ValueError,TypeError):return None
 end=time.monotonic()+limit
 while not j.get("exited") and time.monotonic()<end:
  if not j.get("pid"):return None
  time.sleep(.8)
  p=ssh("nodeb",["qm","guest","exec-status","905",str(j["pid"])],27)
  if not p or p.returncode:return None
  try:j=json.loads(p.stdout)
  except (ValueError,TypeError):return None
 return j if j.get("exited") else None
def cli(args):
 j=qga(["ha",*args,"--no-progress","--raw-json"],75)
 if not j or j.get("exitcode")!=0:return None
 try:
  obj=json.loads(j.get("out-data") or "{}")
  return obj if isinstance(obj,dict) else None
 except (ValueError,TypeError):return None
def inventory():
 d=cli(["apps","list"])
 if not d or d.get("result")!="ok":return None
 a=d.get("data",{})
 a=a.get("apps",a.get("addons")) if isinstance(a,dict) else a
 if not isinstance(a,list):return None
 return [x for x in a if isinstance(x,dict) and x.get("slug")==APP]
def info():
 d=cli(["apps","info",APP])
 return (d or {}).get("data",{}) if d and d.get("result")=="ok" else {}
def safety():
 a=ssh("nodea",["qm","status","906"],22);b=ssh("nodeb",["qm","status","905"],22)
 if not a or not b or a.returncode or b.returncode or a.stdout.strip()!="status: running" or b.stdout.strip()!="status: running":return False
 secret=qga(["sh","-c","test ! -e "+shlex.quote(SECRET)+" && test ! -L "+shlex.quote(SECRET)],45)
 if not secret or secret.get("exitcode")!=0:return False
 # A source VM is active. The temporary app must have no live ESPHome
 # integration on this target. This is checked by the shared diagnostics too.
 code='''import pathlib,json
p=pathlib.Path("/config/.storage/core.config_entries")
a=json.loads(p.read_text()).get("data",{}).get("entries",[])
n=sum(x.get("domain")=="esphome" for x in a if isinstance(x,dict))
print("JNS_TEMP_TARGET_ESP="+str(n))'''
 tag=base64.b64encode(code.encode()).decode()
 c=qga(["docker","exec","homeassistant","python3","-c",
        "exec(__import__('base64').b64decode("+repr(tag)+"))"],55)
 return bool(c and c.get("exitcode")==0 and "JNS_TEMP_TARGET_ESP=0" in str(c.get("out-data","")))
def main():
 if os.uname().nodename.split(".")[0]!="nodec" or not safety():
  note("BLOCKED","source_target_or_secret_safety_gate");return 1
 current=inventory()
 if current is None or len(current)!=1 or info().get("repository")!="local" or info().get("version")!="0.1.0":
  note("BLOCKED","unexpected_installed_app_identity");return 1
 if info().get("state") not in ("error","stopped"):
  note("BLOCKED","addon_not_in_known_terminal_state");return 1
 note("PREFLIGHT","source_live_target_zero_app_installed_secret_absent")
 removal=cli(["apps","uninstall",APP])
 note("UNINSTALL_SUPERVISOR_RESULT",str((removal or {}).get("result","unknown"))[:20])
 absent=False
 for i in range(25):
  xs=inventory()
  if xs is not None and len(xs)==0:
   absent=True;break
  time.sleep(2)
 if not absent:
  note("BLOCKED","temporary_app_uninstall_not_verified");return 1
 note("UNINSTALL_INVENTORY","confirmed_absent")
 if not safety():
  note("BLOCKED","safety_gate_changed_after_uninstall");return 1
 try:p=subprocess.run(["python3",str(ROOT/"ha905_security_esphome_install_stopped_guarded_20261028.py")],
                   capture_output=True,text=True,timeout=750)
 except (OSError,subprocess.TimeoutExpired):
  note("BLOCKED","stopped_installer_timeout");return 1
 for line in p.stdout.splitlines():
  if line.startswith("JNS_SECURITY_APP_PREP_") and len(line)<240:print(line,flush=True)
 if p.returncode:
  note("BLOCKED","stopped_installer_failed");return 1
 final=inventory()
 if not safety() or final is None or len(final)!=1 or info().get("state")!="stopped":
  note("BLOCKED","post_install_not_stopped_or_state_changed");return 1
 note("RESULT","installed_and_stopped_after_no_secret_smoke_source_still_active")
 return 0
if __name__=="__main__":sys.exit(main())
