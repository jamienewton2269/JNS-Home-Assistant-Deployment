#!/usr/bin/env python3
"""Post-onsite VERIFIED acceptance. Never delete VM906 or its backups.

Manual workflow only. All security functionality must have been physically
checked by the operator. At most delete the verified temporary local app.
"""
import base64,json,os,pathlib,re,shlex,subprocess,sys,time
SSH=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=6"]
SLUG="local_jns_ha905_security_handover"
APPDIR="/mnt/data/supervisor/apps/local/jns_ha905_security_handover"
FILES=("config.yaml","Dockerfile","run.sh","flow.py")
INSPECT=r'''import json,pathlib
d=json.loads(pathlib.Path("/config/.storage/core.config_entries").read_text()).get("data",{}).get("entries",[])
e=json.loads(pathlib.Path("/config/.storage/core.entity_registry").read_text()).get("data",{}).get("entities",[])
active=sum(x.get("domain")=="esphome" and not x.get("disabled_by") for x in d if isinstance(x,dict))
count=sum(x.get("platform")=="esphome" and not x.get("disabled_by") for x in e if isinstance(x,dict))
p=pathlib.Path("/config/packages/jns_ha_security_native_cutover_20261028_v2.yaml")
s=p.read_text() if p.is_file() else ""
print("JNS_ACCEPT_TARGET="+json.dumps({"esphome_entries":active,"esphome_entities":count,
 "native_alarm_yaml":("alarm_control_panel:" in s),"six_automations_defined":s.count("initial_state: false")==6},sort_keys=True))
'''
def note(k,v):print("JNS_SECURITY_ACCEPT_"+k+"="+str(v),flush=True)
def ssh(n,argv,timeout=35):
 try:return subprocess.run(SSH+[n,shlex.join(argv)],capture_output=True,text=True,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):return None
def qga(argv,timeout=90):
 p=ssh("nodeb",["qm","guest","exec","905","--",*argv],34)
 if not p or p.returncode:return None
 try:j=json.loads(p.stdout)
 except (ValueError,TypeError):return None
 deadline=time.monotonic()+timeout
 while not j.get("exited") and time.monotonic()<deadline:
  if not j.get("pid"):return None
  time.sleep(.7)
  p=ssh("nodeb",["qm","guest","exec-status","905",str(j["pid"])],24)
  if not p or p.returncode:return None
  try:j=json.loads(p.stdout)
  except (ValueError,TypeError):return None
 return j if j.get("exited") else None
def state():
 b=base64.b64encode(INSPECT.encode()).decode()
 j=qga(["docker","exec","homeassistant","python3","-c",
        "exec(__import__('base64').b64decode("+repr(b)+"))"],45)
 if not j or j.get("exitcode")!=0:return None
 lines=[x.split("=",1)[1] for x in str(j.get("out-data","")).splitlines() if x.startswith("JNS_ACCEPT_TARGET=")]
 try:return json.loads(lines[0]) if len(lines)==1 else None
 except (ValueError,TypeError):return None
def app_info():
 j=qga(["ha","apps","info",SLUG,"--no-progress","--raw-json"],45)
 if not j or j.get("exitcode")!=0:return {}
 try:
  v=json.loads(j.get("out-data") or "{}")
  return v.get("data",{}) if v.get("result")=="ok" else {}
 except (ValueError,TypeError):return {}
def main():
 if os.uname().nodename.split(".")[0]!="nodec" or os.environ.get("JNS_ONSITE_PHYSICAL_SECURITY_CHECKS_PASSED")!="true":
  note("BLOCKED","operator_confirmation_or_identity");return 1
 a=ssh("nodea",["qm","status","906"],22)
 b=ssh("nodeb",["qm","status","905"],22)
 if not a or not b or a.stdout.strip()!="status: stopped" or b.stdout.strip()!="status: running":
  note("BLOCKED","exclusive_status");return 1
 t=state()
 if not t or t.get("esphome_entries")!=1 or t.get("esphome_entities",0)<30 or not t.get("native_alarm_yaml") or not t.get("six_automations_defined"):
  note("BLOCKED","native_owner_or_alarm_entities_not_verified");return 1
 note("TARGET",json.dumps(t,sort_keys=True))
 if not app_info() or app_info().get("repository")!="local":
  note("BLOCKED","temporary_app_identity");return 1
 # Final acceptance marker takes precedence over the deadline: only AFTER
 # physical acceptance and current sole-owner verification.
 MARK=r'''import pathlib,os,time,json
p=pathlib.Path("/var/lib/jns-solar/consolidation/vm906-handover-complete-20261028")
if os.geteuid()!=0 or os.uname().nodename.split(".")[0]!="nodea":raise SystemExit(70)
if p.exists() or p.is_symlink():raise SystemExit(71)
with p.open("x") as f:
 json.dump({"accepted_utc_epoch":int(time.time()),"vm905":905,"retained_fallback_vm906":906},f)
 f.flush();os.fsync(f.fileno())
p.chmod(0o600)
print("JNS_HANDOVER_ACCEPTANCE_MARKER=written")
'''
 mark=ssh("nodea",["python3","-c",MARK],45)
 if not mark or mark.returncode or "JNS_HANDOVER_ACCEPTANCE_MARKER=written" not in mark.stdout:
  note("BLOCKED","acceptance_marker_not_written");return 1
 note("ACCEPTED","VM905_single_owner_VM906_retained_stopped")
 # Disable Node A local timer; accepted marker additionally prevents rollback.
 timer=ssh("nodea",["systemctl","stop","jns-ha906-recovery-20261028.timer"],25)
 note("NODEA_TIMER_DISABLED",str(bool(timer and timer.returncode==0)).lower())
 # Stop and uninstall ONLY the vetted transient enrolment app. Do not alter
 # target native ESPHome entry or package and do not stop VM905 Core.
 qga(["ha","apps","stop",SLUG,"--no-progress","--raw-json"],45)
 qga(["ha","apps","uninstall",SLUG,"--no-progress","--raw-json"],180)
 removed=False
 for i in range(20):
  k=app_info()
  if not k or k.get("installed") is False:
   removed=True;break
  time.sleep(2)
 if removed:
  files=" ".join(shlex.quote(APPDIR+"/"+s) for s in FILES)
  cmd="rm -f "+files+" && rmdir "+shlex.quote(APPDIR)
  j=qga(["sh","-c",cmd],65)
  cleaned=bool(j and j.get("exitcode")==0)
 else:cleaned=False
 note("APP_UNINSTALLED",str(removed).lower())
 note("APP_SOURCE_REMOVED",str(cleaned).lower())
 # Keep Node C fallback data for audit, but disable its cron hook now that
 # Node A carries the durable acceptance marker.
 try:
  listing=subprocess.run(["crontab","-l"],capture_output=True,text=True,timeout=15)
  old=listing.stdout if listing.returncode==0 else ""
  filtered=[row for row in old.splitlines() if "# jns-security-exclusive-failback-20261028" not in row]
  done=subprocess.run(["crontab","-"],input="\n".join(filtered)+"\n",text=True,capture_output=True,timeout=22)
  cron_removed=done.returncode==0
 except (OSError,subprocess.TimeoutExpired):cron_removed=False
 note("NODEC_FAILBACK_CRON_DISABLED",str(cron_removed).lower())
 remaining=state()
 if not remaining or remaining.get("esphome_entries")!=1:
  note("BLOCKED","post_acceptance_owner_health");return 1
 return 0 if removed and cleaned and cron_removed and timer and timer.returncode==0 else 1
if __name__=="__main__":sys.exit(main())
