#!/usr/bin/env python3
"""One user-authorised read-only GET probe from installed/stopped HA905 app.

No installation/build/reinstall, ESPHome enrolment, config-flow, alarm actions,
Core restart or guest power changes. On completion (including failures),
stop/uninstall this one verified temporary app and safely remove its source.
No app tokens, API response bodies, or unfiltered logs are emitted.
"""
import base64,json,os,shlex,subprocess,sys,time
SSH=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=6"]
HOST=r'''
import json,os,pathlib,re,subprocess,time
if os.geteuid()!=0 or os.uname().nodename.split(".")[0]!="nodeb":raise SystemExit(70)
slug="local_jns_ha905_core_api_probe"
source="/mnt/data/supervisor/apps/local/jns_ha905_core_api_probe"
stage=pathlib.Path("/var/lib/jns-solar/consolidation/ha905-core-api-bridge-probe-20261028-v1")
marker=stage/"core-api-one-start-20261028.json"
expected_sha="b9ec7544eea8686f0a64f45945aed6f93c295ea82ea78c7efd3bcdc9dcbc1db3"
def note(k,v):print("JNS_HA905_API_TEST_"+k+"="+str(v),flush=True)
def host(args,timeout=30):
 try:return subprocess.run(args,capture_output=True,text=True,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):return None
def run(argv,timeout=120):
 p=host(["qm","guest","exec","905","--",*argv])
 if not p or p.returncode:return None
 try:j=json.loads(p.stdout)
 except ValueError:return None
 deadline=time.monotonic()+timeout
 while not j.get("exited") and time.monotonic()<deadline:
  if not j.get("pid"):return None
  time.sleep(.5)
  p=host(["qm","guest","exec-status","905",str(j["pid"])],25)
  if not p or p.returncode:return None
  try:j=json.loads(p.stdout)
  except ValueError:return None
 return j if j.get("exited") else None
def shell(text,timeout=90):return run(["sh","-c",text],timeout)
def stdout(j):return str(j.get("out-data","")) if j else ""
def decoded_info():
 j=run(["ha","apps","info",slug,"--no-progress","--raw-json"],45)
 if not j or j.get("exitcode")!=0:return {}
 try:
  d=json.loads(stdout(j))
  if not isinstance(d,dict) or d.get("result")!="ok":return {}
  info=d.get("data",{})
  return info if isinstance(info,dict) else {}
 except ValueError:return {}
status=host(["qm","status","905"])
if not status or status.returncode or status.stdout.strip()!="status: running":
 note("BLOCKED","target_offline");raise SystemExit(71)
info=decoded_info()
if not (info.get("version")=="0.1.0" and info.get("state")=="stopped"
        and info.get("repository")=="local"):
 note("BLOCKED","not_exact_expected_stopped_local_app");raise SystemExit(72)
check=shell('test -f '+source+'/Dockerfile && test ! -L '+source+'/Dockerfile && test "$(sha256sum '+source+'/Dockerfile | cut -d" " -f1)" = "'+expected_sha+'"')
if not check or check.get("exitcode")!=0:
 note("BLOCKED","reviewed_source_mismatch");raise SystemExit(73)
if marker.exists() or marker.is_symlink():
 note("BLOCKED","one_shot_already_recorded");raise SystemExit(74)
if not stage.is_dir() or stage.is_symlink():
 note("BLOCKED","private_stage_missing");raise SystemExit(75)
# Marker is created before any startup. One controlled start maximum.
with marker.open("x") as f:
 json.dump({"target_vm":905,"read_only_one_start":True,"status":"start_requested"},f)
 f.write("\n")
marker.chmod(0o600)
note("PREREQUISITES","verified")
started=False
got_result=False
both_200=False
uninstalled=False
source_removed=False
try:
 started=True
 p=run(["ha","apps","start",slug,"--no-progress","--raw-json"],70)
 start_result="unknown"
 if p:
  try:
   j=json.loads(stdout(p))
   if isinstance(j,dict):start_result=str(j.get("result","unknown"))
  except ValueError:pass
 note("START_API_RESULT",start_result)
 for i in range(16):
  time.sleep(1.5)
  p=run(["ha","apps","logs",slug,"--lines","100"],35)
  if not p:continue
  lines=re.findall(r"JNS_HA905_TRUSTED_APP_CORE_PREFLIGHT=(\{[^\r\n]*\})",stdout(p))
  if not lines:continue
  try:j=json.loads(lines[-1])
  except ValueError:continue
  if not isinstance(j,dict) or j.get("read_only") is not True or j.get("esphome_enrolled") is not False:continue
  got_result=True
  note("CORE_ROOT_HTTP",j.get("core_root_http","unknown"))
  note("CORE_CONFIG_HTTP",j.get("core_config_http","unknown"))
  both_200=j.get("core_root_http")==200 and j.get("core_config_http")==200
  break
 note("CORE_GET_RESULT_RECORDED",str(got_result).lower())
finally:
 # The user authorised this app only for the single read-only test.
 # Stop and uninstall regardless of whether either GET succeeded.
 shell("ha apps stop "+slug+" --no-progress --raw-json >/dev/null 2>&1 || true",45)
 shell("ha apps uninstall "+slug+" --no-progress --raw-json >/dev/null 2>&1 || true",145)
 until=time.monotonic()+95
 while time.monotonic()<until:
  p=run(["ha","apps","info",slug,"--no-progress","--raw-json"],35)
  if p:
   try:
    j=json.loads(stdout(p))
    x=j.get("data",{}) if isinstance(j,dict) else {}
    if (isinstance(j,dict) and (j.get("result")=="error" or
        (j.get("result")=="ok" and isinstance(x,dict) and x.get("installed") is False))):
     uninstalled=True
     break
   except ValueError:pass
  time.sleep(3)
 if uninstalled:
  p=shell("rm -f "+source+"/config.yaml "+source+"/Dockerfile "+source+
   "/probe.py "+source+"/run.sh && rmdir "+source,75)
  source_removed=bool(p and p.get("exitcode")==0)
  if source_removed:
   shell("ha store reload --no-progress >/dev/null 2>&1",90)
 note("UNINSTALLED_VERIFIED",str(uninstalled).lower())
 note("SOURCE_REMOVED_VERIFIED",str(source_removed).lower())
 note("NO_ESPHOME_OPERATION","yes")
if not got_result or not both_200 or not uninstalled or not source_removed:
 raise SystemExit(80)
note("RESULT","authenticated_readonly_core_get_200")
'''
def ssh(node,args,timeout=30):
 try:return subprocess.run(SSH+[node,shlex.join(args)],capture_output=True,text=True,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):return None
def main():
 if os.uname().nodename.split(".")[0]!="nodec":
  print("JNS_HA905_READONLY_ONCE_BLOCKED=wrong_runner");return 1
 for node,vm in (("nodea",906),("nodeb",905),("nodea",902)):
  p=ssh(node,["qm","status",str(vm)],18)
  if not p or p.returncode or p.stdout.strip()!="status: running":
   print("JNS_HA905_READONLY_ONCE_BLOCKED=required_VM_offline");return 1
 code=base64.b64encode(HOST.encode()).decode()
 args=["python3","-u","-c","exec(__import__('base64').b64decode('"+code+"'))"]
 try:p=subprocess.run(SSH+["nodeb",shlex.join(args)],capture_output=True,text=True,timeout=690)
 except (OSError,subprocess.TimeoutExpired):
  print("JNS_HA905_READONLY_ONCE_BLOCKED=host_timeout");return 1
 lines=[x for x in p.stdout.splitlines() if x.startswith("JNS_HA905_API_TEST_")]
 for line in lines:print(line,flush=True)
 if p.returncode or not any(x.endswith("RESULT=authenticated_readonly_core_get_200") for x in lines):
  print("JNS_HA905_READONLY_ONCE_BLOCKED=verification_or_cleanup_not_confirmed");return 1
 v=ssh("nodea",["qm","status","906"],18)
 if not v or v.returncode or v.stdout.strip()!="status: running":
  print("JNS_HA905_READONLY_ONCE_BLOCKED=source_state_changed");return 1
 print("JNS_HA905_READONLY_CORE_API_PROVEN_AND_APP_REMOVED=yes")
 return 0
if __name__=="__main__":sys.exit(main())
