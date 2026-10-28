#!/usr/bin/env python3
"""No-secret smoke test of installed HA905 native ESPHome flow app.

NO enrollment secrets are staged. VM906 remains running. Refuse when anything
suggests the app could connect to a real ESPHome device. Do not print logs.
"""
import base64,json,os,pathlib,re,shlex,subprocess,sys,time
SSH=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=6"]
SLUG="local_jns_ha905_security_handover"
SECRET="/mnt/data/supervisor/share/jns-security-handover-20261028/enrolment.json"
COUNT=r'''import json,pathlib
p=pathlib.Path("/config/.storage/core.config_entries")
d=json.loads(p.read_text()).get("data",{}).get("entries",[])
v=[x for x in d if isinstance(x,dict) and x.get("domain")=="esphome"]
print("JNS_ESP_REGISTRY_COUNT="+str(len(v)))
'''
def note(k,v):print("JNS_ESPHOME_NO_SECRET_SMOKE_"+k+"="+str(v),flush=True)
def ssh(host,argv,timeout=36):
 try:return subprocess.run(SSH+[host,shlex.join(argv)],capture_output=True,text=True,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):return None
def qga(args,timeout=80):
 p=ssh("nodeb",["qm","guest","exec","905","--",*args],38)
 if not p or p.returncode:return None
 try:j=json.loads(p.stdout)
 except (ValueError,TypeError):return None
 end=time.monotonic()+timeout
 while not j.get("exited") and time.monotonic()<end:
  if not j.get("pid"):return None
  time.sleep(.6)
  p=ssh("nodeb",["qm","guest","exec-status","905",str(j["pid"])],25)
  if not p or p.returncode:return None
  try:j=json.loads(p.stdout)
  except (ValueError,TypeError):return None
 return j if j.get("exited") else None
def core_count():
 code=base64.b64encode(COUNT.encode()).decode()
 j=qga(["docker","exec","homeassistant","python3","-c",
        "exec(__import__('base64').b64decode("+repr(code)+"))"],65)
 if not j or j.get("exitcode")!=0:return None
 lines=[z.split("=",1)[1] for z in str(j.get("out-data","")).splitlines()
        if z.startswith("JNS_ESP_REGISTRY_COUNT=")]
 return int(lines[0]) if len(lines)==1 and lines[0].isdigit() else None
def supervisor_data(args):
 j=qga(["ha",*args,"--no-progress","--raw-json"],75)
 if not j or j.get("exitcode")!=0:return None
 try:
  data=json.loads(j.get("out-data") or "{}")
  if data.get("result")!="ok":return None
  return data.get("data")
 except (ValueError,TypeError):return None
def check():
 s=ssh("nodea",["qm","status","906"],25)
 t=ssh("nodeb",["qm","status","905"],25)
 if not s or not t or s.returncode or t.returncode or s.stdout.strip()!="status: running" or t.stdout.strip()!="status: running":
  note("BLOCKED","vm_status");return False
 j=qga(["sh","-c","test ! -e "+shlex.quote(SECRET)+" && test ! -L "+shlex.quote(SECRET)],40)
 if not j or j.get("exitcode")!=0:
  note("BLOCKED","private_secret_not_proven_absent");return False
 if core_count()!=0:
  note("BLOCKED","target_esphome_entries_present");return False
 items=supervisor_data(["apps","list"])
 addons=items.get("apps",items.get("addons")) if isinstance(items,dict) else items
 if not isinstance(addons,list) or sum(a.get("slug")==SLUG and a.get("installed") is not False
         for a in addons if isinstance(a,dict))!=1:
  note("BLOCKED","not_installed_inventory");return False
 obj=supervisor_data(["apps","info",SLUG])
 if not isinstance(obj,dict) or obj.get("state")!="stopped" or obj.get("repository")!="local":
  note("BLOCKED","app_not_stopped_local");return False
 return True
def main():
 if os.uname().nodename.split(".")[0]!="nodec":return 1
 if not check():return 1
 note("PREREQUISITES","source_active_target_zero_integrations_secret_absent_app_stopped")
 j=qga(["ha","apps","start",SLUG,"--no-progress","--raw-json"],120)
 status="ok" if j and j.get("exitcode")==0 else "failed"
 if j:
  try:status=str(json.loads(j.get("out-data") or "{}").get("result",status))[:24]
  except (ValueError,TypeError):pass
 note("START_CLI_RESULT",status)
 blocked=False
 for _ in range(22):
  lg=qga(["ha","apps","logs",SLUG,"--lines","100"],45)
  if lg:
   l=str(lg.get("out-data",""))
   # Do not disclose or echo any log lines.
   if "JNS_ESP_HANDOVER_ENTRY_CREATED=yes" in l or "JNS_ESP_HANDOVER_NATIVE_CONFIG_FLOW_COMPLETE=yes" in l:
    note("BLOCKED","unexpected_native_flow_activity");return 1
   if "JNS_ESP_HANDOVER_BLOCKED=private_enrolment_stage_missing" in l:
    blocked=True;break
   if "JNS_ESP_HANDOVER_BLOCKED=one_shot_already_attempted" in l:
    note("BLOCKED","app_data_marker_from_previous_attempt");break
   if "JNS_ESP_HANDOVER_BLOCKED=supervisor_token_absent" in l:
    note("BLOCKED","supervisor_token_missing");break
  time.sleep(2)
 if not blocked:
  note("BLOCKED","expected_absent_secret_exit_not_proven");return 1
 if not check():
  # check() requires the app stopped; a short wait can accommodate once-exit.
  time.sleep(4)
  if not check():
   note("BLOCKED","post_smoke_safe_state_unconfirmed");return 1
 note("RESULT","app_runtime_proven_no_secret_no_config_flow_source_live")
 return 0
if __name__=="__main__":sys.exit(main())
