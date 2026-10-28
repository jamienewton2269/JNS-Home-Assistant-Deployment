#!/usr/bin/env python3
"""Execute exactly one native ESPHome enrolment after exclusive source fencing.

Run ONLY on Node C from the on-site-approved manual cutover workflow.
The source ESPHome record never leaves Node B's private host staging area.
No app service calls, alarm commands, .storage edits, or secret output.
"""
import base64,json,os,pathlib,re,shlex,subprocess,sys,time
SSH=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=6"]
SLUG="local_jns_ha905_security_handover"
PRIVHOST=r'''
import json,os,pathlib,subprocess,base64,time,shlex
if os.geteuid()!=0 or os.uname().nodename.split(".")[0]!="nodeb":raise SystemExit(71)
root=pathlib.Path("/var/lib/jns-solar/consolidation/ha-security-906-20261027-v1")
entry=root/"esphome-enrolment-private.json"
manifest=root/"manifest.json"
if entry.is_symlink() or manifest.is_symlink() or not entry.is_file() or not manifest.is_file():raise SystemExit(72)
m=json.loads(manifest.read_text())
if m.get("source_vm")!=906 or m.get("target_vm")!=905:raise SystemExit(73)
record=json.loads(entry.read_text())
if record.get("domain")!="esphome" or not isinstance(record.get("data"),dict):raise SystemExit(74)
data=record["data"]
host=data.get("host") or data.get("ip_address")
port=data.get("port",6053)
key=data.get("noise_psk")
password=data.get("password") or ""
if not isinstance(host,str) or not 1<=len(host)<=255:raise SystemExit(75)
if not isinstance(port,int) or not 1<=port<=65535:raise SystemExit(76)
if not isinstance(key,str) or len(key)<40 or not isinstance(password,str):raise SystemExit(77)
payload=json.dumps({"source_vm":906,"target_vm":905,
 "single_controller_gate":"vm906_stopped_recovery_armed",
 "esphome":{"host":host,"port":port,"noise_psk":key,"password":password}},separators=(",",":")).encode()
def qga(argv,timeout=70):
 p=subprocess.run(["qm","guest","exec","905","--",*argv],capture_output=True,text=True,timeout=25)
 if p.returncode:raise SystemExit(78)
 j=json.loads(p.stdout);end=time.monotonic()+timeout
 while not j.get("exited") and time.monotonic()<end:
  time.sleep(.7)
  p=subprocess.run(["qm","guest","exec-status","905",str(j["pid"])],capture_output=True,text=True,timeout=23)
  if p.returncode:raise SystemExit(79)
  j=json.loads(p.stdout)
 if not j.get("exited") or j.get("exitcode")!=0:raise SystemExit(80)
 return j
# The secret only crosses the local Node B host-to-HAOS QGA boundary.
path="/mnt/data/supervisor/share/jns-security-handover-20261028"
enc=base64.b64encode(payload).decode()
cmd="umask 077; test ! -e "+shlex.quote(path+"/enrolment.json")+" && mkdir -p "+shlex.quote(path)+ \
"; printf '%s' "+shlex.quote(enc)+" | base64 -d > "+shlex.quote(path+"/enrolment.json")+ \
"; chmod 0600 "+shlex.quote(path+"/enrolment.json")
qga(["sh","-c",cmd],90)
# Verify only existence+permissions, NEVER print the secret contents.
qga(["sh","-c","test -s "+shlex.quote(path+"/enrolment.json")+" && test ! -L "+shlex.quote(path+"/enrolment.json")],35)
print("JNS_ENROL_PRIVATE_STAGE=verified_no_secret_output",flush=True)
'''
STATE_SCRIPT=r'''import json,pathlib
p=pathlib.Path("/config/.storage/core.config_entries")
d=json.loads(p.read_text()).get("data",{}).get("entries",[])
entry=[x for x in d if isinstance(x,dict) and x.get("domain")=="esphome" and not x.get("disabled_by")]
p=pathlib.Path("/config/.storage/core.entity_registry")
e=json.loads(p.read_text()).get("data",{}).get("entities",[])
n=sum(x.get("platform")=="esphome" and not x.get("disabled_by") for x in e if isinstance(x,dict))
print("JNS_NATIVE_ENROL_RESULT="+json.dumps({"active_esphome_entries":len(entry),"registered_esphome_entities":n},sort_keys=True))
'''
def ssh(node,argv,timeout=30):
 try:return subprocess.run(SSH+[node,shlex.join(argv)],capture_output=True,text=True,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):return None
def qga(args,timeout=100):
 p=ssh("nodeb",["qm","guest","exec","905","--",*args],35)
 if not p or p.returncode:return None
 try:j=json.loads(p.stdout)
 except (ValueError,TypeError):return None
 deadline=time.monotonic()+timeout
 while not j.get("exited") and time.monotonic()<deadline:
  if not j.get("pid"):return None
  time.sleep(.8)
  p=ssh("nodeb",["qm","guest","exec-status","905",str(j["pid"])],26)
  if not p or p.returncode:return None
  try:j=json.loads(p.stdout)
  except (ValueError,TypeError):return None
 return j if j.get("exited") and not j.get("out-truncated") else None
def node_status(node,vm):
 r=ssh(node,["qm","status",str(vm)],20)
 return (r.stdout.strip() if r and r.returncode==0 else None)
def info():
 j=qga(["ha","apps","info",SLUG,"--raw-json","--no-progress"],50)
 if not j or j.get("exitcode")!=0:return {}
 try:
  k=json.loads(j.get("out-data") or "{}")
  return k.get("data",{}) if k.get("result")=="ok" else {}
 except (ValueError,TypeError):return {}
def app_cleanup():
 # Only remove short-lived copied credentials. Integration's own secure
 # config entry is retained for on-site verification.
 path="/mnt/data/supervisor/share/jns-security-handover-20261028"
 cmd="rm -f "+shlex.quote(path+"/enrolment.json")+" && rmdir "+shlex.quote(path)
 j=qga(["sh","-c",cmd],50)
 return bool(j and j.get("exitcode")==0)
def main():
 if os.uname().nodename.split(".")[0]!="nodec":
  print("JNS_ENROL_BLOCKED=runner_identity");return 1
 if node_status("nodea",906)!="status: stopped" or node_status("nodeb",905)!="status: running":
  print("JNS_ENROL_BLOCKED=exclusive_source_not_stopped");return 1
 timer=ssh("nodea",["systemctl","is-active","jns-ha906-recovery-20261028.timer"],20)
 if not timer or timer.returncode or timer.stdout.strip()!="active":
  print("JNS_ENROL_BLOCKED=nodea_fence_gated_recovery_timer_inactive");return 1
 recovery=pathlib.Path.home()/".local/share/jns-security-failback-20261028/state.json"
 if not recovery.is_file() or recovery.is_symlink():
  print("JNS_ENROL_BLOCKED=nodec_auto_recovery_not_armed");return 1
 try:
  r=json.loads(recovery.read_text())
  if r.get("source_vm")!=906 or r.get("target_vm")!=905 or r.get("deadline",0)<time.time()+90:
   raise ValueError
 except (OSError,ValueError,TypeError):
  print("JNS_ENROL_BLOCKED=recovery_window_not_valid");return 1
 original=info()
 if not original or original.get("repository")!="local" or original.get("version")!="0.1.0" or original.get("state")!="stopped":
  print("JNS_ENROL_BLOCKED=expected_stopped_temporary_app_missing");return 1
 secret_prepared=False
 try:
  priv=base64.b64encode(PRIVHOST.encode()).decode()
  # Cleanup also runs when the remote copy has an ambiguous outcome.
  secret_prepared=True
  run=ssh("nodeb",["python3","-u","-c","exec(__import__('base64').b64decode("+repr(priv)+"))"],140)
  if not run or run.returncode or "JNS_ENROL_PRIVATE_STAGE=verified_no_secret_output" not in run.stdout:
   print("JNS_ENROL_BLOCKED=private_key_transfer_failed");return 1
  print("JNS_ENROL_PRIVATE_STAGE=verified",flush=True)
  if node_status("nodea",906)!="status: stopped":
   print("JNS_ENROL_BLOCKED=source_owner_changed");return 1
  # The first start is the ONE native integration config-flow attempt.
  qga(["ha","apps","start",SLUG,"--no-progress","--raw-json"],110)
  success=False
  for i in range(35):
   j=qga(["ha","apps","logs",SLUG,"--lines","100"],40)
   if j:
    logs=str(j.get("out-data",""))
    if "JNS_ESP_HANDOVER_ENTRY_CREATED=yes" in logs and "JNS_ESP_HANDOVER_NATIVE_CONFIG_FLOW_COMPLETE=yes" in logs:
     success=True;break
    if "JNS_ESP_HANDOVER_BLOCKED=" in logs or "JNS_ESP_HANDOVER_FLOW_EXCEPTION_CLASS=" in logs:
     break
   time.sleep(2)
  if not success:
   print("JNS_ENROL_BLOCKED=native_flow_not_proven");return 1
  reg=base64.b64encode(STATE_SCRIPT.encode()).decode()
  for i in range(30):
   j=qga(["docker","exec","homeassistant","python3","-c",
          "exec(__import__('base64').b64decode("+repr(reg)+"))"],45)
   if j and j.get("exitcode")==0:
    lines=[x.split("=",1)[1] for x in (j.get("out-data") or "").splitlines()
           if x.startswith("JNS_NATIVE_ENROL_RESULT=")]
    try:
     obj=json.loads(lines[0]) if len(lines)==1 else None
    except (ValueError,TypeError):obj=None
    if obj and obj.get("active_esphome_entries")==1 and obj.get("registered_esphome_entities",0)>=30:
     print("JNS_ENROL_VERIFIED="+json.dumps(obj,sort_keys=True),flush=True)
     print("JNS_ENROL_RESULT=await_on_site_physical_inputs_check",flush=True)
     return 0
   time.sleep(3)
  print("JNS_ENROL_BLOCKED=integration_entities_unconfirmed");return 1
 finally:
  if secret_prepared:
   print("JNS_ENROL_SHORT_LIVED_KEY_REMOVED="+str(app_cleanup()).lower(),flush=True)
if __name__=="__main__":sys.exit(main())
