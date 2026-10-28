#!/usr/bin/env python3
"""Safely resume HA-General after a failed security integration transfer.

Preconditions: exclusive source VM906 running, target VM905 PAUSED, onsite
operator previously authorised this cutover. VM906 must be STOPPED before
VM905 resumes. Stop/uninstall transient ESPHome flow app and prove NO new
ESPHome integration twice before restoring VM906. All failure branches call
exclusive target-fence-first recovery. NEVER resume target with VM906 active.
"""
import base64,json,os,pathlib,re,shlex,subprocess,sys,time
SSH=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=6"]
SOURCE=pathlib.Path(__file__).parent
FALLBACK=SOURCE/"ha906_nodec_auto_failback_20261028.py"
SLUG="local_jns_ha905_security_handover"
REG=r'''import json,pathlib
p=pathlib.Path("/config/.storage/core.config_entries")
if not p.is_file() or p.is_symlink():raise SystemExit(71)
entries=json.loads(p.read_text()).get("data",{}).get("entries",[])
assert isinstance(entries,list)
active=[e for e in entries if isinstance(e,dict) and e.get("domain")=="esphome" and not e.get("disabled_by")]
all_entries=[e for e in entries if isinstance(e,dict) and e.get("domain")=="esphome"]
print("JNS_TARGET_ESPHOME="+json.dumps({"entries_all":len(all_entries),"entries_active":len(active)},sort_keys=True))
'''
def note(k,v):print("JNS_HA905_SERVICE_RESTORE_"+k+"="+str(v),flush=True)
def ssh(node,argv,timeout=32):
 try:return subprocess.run(SSH+[node,shlex.join(argv)],capture_output=True,text=True,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):return None
def state(n,vm):
 q=ssh(n,["qm","status",str(vm)],22)
 return q.stdout.strip() if q and q.returncode==0 else None
def identity(n,vm,name):
 p=ssh(n,["qm","config",str(vm)],25)
 return bool(p and p.returncode==0 and re.search("^name: "+re.escape(name)+"$",p.stdout,re.M))
def qga(args,timeout=90):
 p=ssh("nodeb",["qm","guest","exec","905","--",*args],35)
 if not p or p.returncode:return None
 try:j=json.loads(p.stdout)
 except (ValueError,TypeError):return None
 end=time.monotonic()+timeout
 while not j.get("exited") and time.monotonic()<end:
  if not j.get("pid"):return None
  time.sleep(.6)
  p=ssh("nodeb",["qm","guest","exec-status","905",str(j["pid"])],26)
  if not p or p.returncode:return None
  try:j=json.loads(p.stdout)
  except (ValueError,TypeError):return None
 return j if j.get("exited") and not j.get("out-truncated") else None
def appinfo():
 j=qga(["ha","apps","info",SLUG,"--no-progress","--raw-json"],55)
 if not j or j.get("exitcode")!=0:return {}
 try:
  obj=json.loads(j.get("out-data") or "{}")
  return obj.get("data",{}) if obj.get("result")=="ok" else {}
 except (TypeError,ValueError):return {}
def target_integrations():
 encoded=base64.b64encode(REG.encode()).decode()
 j=qga(["docker","exec","homeassistant","python3","-c",
        "exec(__import__('base64').b64decode("+repr(encoded)+"))"],55)
 if not j or j.get("exitcode")!=0:return None
 lines=[line.split("=",1)[1] for line in str(j.get("out-data","")).splitlines() if line.startswith("JNS_TARGET_ESPHOME=")]
 try:return json.loads(lines[0]) if len(lines)==1 else None
 except (ValueError,TypeError):return None
def app_action(action,timeout):
 j=qga(["ha","apps",action,SLUG,"--no-progress","--raw-json"],timeout)
 ok=bool(j and j.get("exitcode")==0)
 note("APP_"+action.upper()+"_EXIT",("success" if ok else "failed_or_unknown"))
 if j:
  try:
   z=json.loads(j.get("out-data") or "{}")
   note("APP_"+action.upper()+"_RESULT",str(z.get("result","none"))[:40])
  except (ValueError,TypeError):pass
 return ok
def installed_app_inventory():
 j=qga(["ha","apps","list","--no-progress","--raw-json"],60)
 if not j or j.get("exitcode")!=0:return None
 try:
  data=json.loads(j.get("out-data") or "{}")
  if data.get("result")!="ok":return None
  section=data.get("data",{})
  apps=(section.get("apps",section.get("addons")) if isinstance(section,dict) else section)
  if not isinstance(apps,list):return None
  return any(isinstance(x,dict) and
   (x.get("slug")==SLUG or x.get("name")=="JNS HA905 Security Handover")
   and x.get("installed") is not False for x in apps)
 except (ValueError,TypeError,AttributeError):return None
def clean_temp_app():
 # Stop first; wait until Supervisor reports stopped; uninstall only then.
 b=appinfo()
 note("APP_INITIAL_STATE",str(b.get("state","unknown"))[:40])
 if b and b.get("repository")!="local":
  note("BLOCKED","temporary_app_unexpected_repository");return False
 if b:
  app_action("stop",110)
  for i in range(18):
   b=appinfo()
   st=b.get("state")
   if st in ("stopped","error","unknown") or not b:break
   time.sleep(2)
  note("APP_AFTER_STOP_STATE",str(b.get("state","not_listed"))[:40])
  # Never allow any remaining running process before uninstall.
  if b and b.get("state") in ("started","running","stopping"):
   note("BLOCKED","flow_app_still_running");return False
  if b:
   app_action("uninstall",170)
  for i in range(15):
   present=installed_app_inventory()
   b=appinfo()
   if present is False or (b.get("installed") is False):
    note("APP_UNINSTALL_INVENTORY","confirmed_absent")
    return True
   if not b and present is None:
    # Info absent alone is insufficient when the inventory is unknown.
    time.sleep(2)
    continue
   time.sleep(2)
  note("APP_UNINSTALL_FINAL_STATE",str(b.get("state","unknown"))[:40])
  note("APP_UNINSTALL_INSTALLED_FIELD",str(b.get("installed","unknown"))[:20])
  note("APP_UNINSTALL_INVENTORY_STATE",str(present)[:20])
  note("BLOCKED","temporary_app_uninstall_not_proven")
  return False
 present=installed_app_inventory()
 if present is False:
  note("TEMP_ENROL_APP","verified_absent")
  return True
 note("BLOCKED","temporary_app_absence_not_proven")
 return False
def rollback():
 try:p=subprocess.run(["python3",str(FALLBACK),"--restore"],capture_output=True,text=True,timeout=255)
 except (OSError,subprocess.TimeoutExpired):p=None
 if p:
  for line in p.stdout.splitlines():
   if line.startswith(("JNS_HA906_SAFE_AUTO_FAILBACK_","JNS_NODEA_")) and len(line)<200:
    print(line,flush=True)
 note("ROLLBACK",("VM906_exclusive_restored" if p and p.returncode==0 and
                      state("nodea",906)=="status: running" and state("nodeb",905)=="status: paused"
                     else "UNVERIFIED_operator_action_needed"))
def main():
 if os.uname().nodename.split(".")[0]!="nodec":
  note("BLOCKED","wrong_gateway");return 1
 if (not identity("nodea",906,"ha-security") or
     not identity("nodeb",905,"ha-s2-general") or
     state("nodea",906)!="status: running" or state("nodeb",905)!="status: paused"):
  note("BLOCKED","exclusive_preconditions");return 1
 t=ssh("nodea",["systemctl","is-active","jns-ha906-recovery-20261028.timer"],20)
 if not t or t.returncode!=0 or t.stdout.strip()!="active":
  note("BLOCKED","source_recovery_timer_missing");return 1
 if not (pathlib.Path.home()/".local/share/jns-security-failback-20261028/state.json").is_file():
  note("BLOCKED","recovery_state_missing");return 1
 successful=False
 source_was_stopped=False
 try:
  note("PHASE","isolate_original_security_controller")
  q=ssh("nodea",["qm","shutdown","906","--timeout","80"],110)
  if state("nodea",906)!="status: stopped":
   note("BLOCKED","source_stop_not_verified");return 1
  source_was_stopped=True
  note("SOURCE","stopped_before_target_resume")
  q=ssh("nodeb",["qm","resume","905"],75)
  if not q or q.returncode!=0 or state("nodeb",905)!="status: running":
   note("BLOCKED","target_resume_failed");return 1
  note("TARGET","resumed_only_with_source_stopped")
  if not clean_temp_app():
   note("BLOCKED","flow_app_not_clean");return 1
  # Double observation with a delay excludes late native config-flow finish
  # after the privilege-bearing app has been uninstalled.
  first=target_integrations()
  if first is None or first.get("entries_all")!=0 or first.get("entries_active")!=0:
   note("BLOCKED","target_esphome_entry_present_or_unknown");return 1
  time.sleep(8)
  second=target_integrations()
  if second is None or second.get("entries_all")!=0 or second.get("entries_active")!=0:
   note("BLOCKED","target_esphome_flow_not_quiescent");return 1
  if state("nodea",906)!="status: stopped" or state("nodeb",905)!="status: running":
   note("BLOCKED","exclusive_states_changed");return 1
  note("TARGET_SECURITY_ENTRY","confirmed_none_twice_flow_app_absent")
  start=ssh("nodea",["qm","start","906"],110)
  if state("nodea",906)!="status: running":
   note("BLOCKED","source_restart_not_verified");return 1
  # Ensure VM905 has no new ESPHome entry after source came up.
  if target_integrations()!={"entries_active":0,"entries_all":0}:
   note("BLOCKED","post_restore_target_owner_changed");return 1
  successful=True
  note("VERIFIED","VM906_running_sole_ESPhome_VM905_running_no_security_entry")
  # Retain source VM906 and all backups. Disarm old recovery timer only
  # after both machines are stable and no new security owner exists.
  t=ssh("nodea",["systemctl","stop","jns-ha906-recovery-20261028.timer"],25)
  note("NODEA_OLD_TIMER_DISABLED",str(bool(t and t.returncode==0)).lower())
  # The NodeC cron can safely remain: source is already running and therefore
  # its restoration path is a no-op. Do not erase forensic state.
  return 0
 finally:
  if not successful and source_was_stopped:
   # If the source came up but a subsequent check became uncertain, never
   # leave two running controllers while another native flow might appear.
   if state("nodea",906)=="status: running" and state("nodeb",905)=="status: running":
    p=ssh("nodeb",["qm","suspend","905"],135)
    note("POST_RESTART_FENCE",("verified" if state("nodeb",905)=="status: paused" else "NOT_VERIFIED"))
   rollback()
if __name__=="__main__":sys.exit(main())
