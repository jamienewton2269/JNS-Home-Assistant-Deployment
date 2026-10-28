#!/usr/bin/env python3
"""Guarded standalone HA905 Core proxy AUTH probe, GET only, VM906 untouched.

Installs an isolated manual-only ephemeral app with homeassistant_api: true.
Collects HTTP status codes, uninstalls, and removes only its verified source.
Never imports private ESPHome credentials, calls a config flow, or stops a VM.
"""
import base64,hashlib,io,json,os,pathlib,re,shlex,subprocess,sys,tarfile,time
ROOT=pathlib.Path(__file__).parent/"ha905_core_auth_readonly_app"
FILES=("config.yaml","Dockerfile","run.sh","probe.py")
NAME="jns_ha905_core_auth_readonly"
SLUG="local_"+NAME
GUEST_ROOT="/mnt/data/supervisor/apps/local"
FOLDER=GUEST_ROOT+"/"+NAME
SSH=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=6"]
TOKEN_FIELDS={"token_present","read_only","posted_config_flow","used_security_output","logged_token"}
ALLOWED_STATUSES={200,201,204,400,401,403,404,405,409,422,429,500,502,503,504,"other_status","token_absent","transport_unavailable","identifier_invalid","not_attempted"}
def note(label,value):
 print("JNS_CORE_AUTH_ONCE_"+label+"="+str(value),flush=True)
def shell(node,args,timeout=40):
 try:return subprocess.run(SSH+[node,shlex.join(args)],
   capture_output=True,text=True,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):return None
def status(node,vm):
 p=shell(node,["qm","status",str(vm)],25)
 return p.stdout.strip() if p and p.returncode==0 else None
def safe_owners():
 return status("nodea",906)=="status: running" and status("nodeb",905)=="status: running"
def guest(args,seconds=115):
 # QGA invocation may be short while the process finishes asynchronously.
 cmd=["qm","guest","exec","905","--timeout",str(max(30,min(240,seconds))),"--",*args]
 p=shell("nodeb",cmd,seconds+45)
 if not p or p.returncode:return None
 try:j=json.loads(p.stdout)
 except (TypeError,ValueError):return None
 deadline=time.monotonic()+seconds
 while not j.get("exited") and time.monotonic()<deadline:
  if not j.get("pid"):return None
  time.sleep(.8)
  p=shell("nodeb",["qm","guest","exec-status","905",str(j["pid"])],28)
  if not p or p.returncode:return None
  try:j=json.loads(p.stdout)
  except (TypeError,ValueError):return None
 return j if j.get("exited") and not j.get("out-truncated") else None
def good(j):return j is not None and j.get("exitcode")==0
def gsh(cmd,seconds=100):return guest(["sh","-c",cmd],seconds)
def info():
 j=guest(["ha","apps","info",SLUG,"--no-progress","--raw-json"],45)
 if not good(j):return None
 try:
  v=json.loads(j.get("out-data") or "{}")
  return v.get("data") if v.get("result")=="ok" and isinstance(v.get("data"),dict) else None
 except (TypeError,ValueError):return None
def inventory():
 j=guest(["ha","apps","list","--no-progress","--raw-json"],45)
 if not good(j):return None
 try:
  r=json.loads(j.get("out-data") or "{}")
  d=r.get("data",{})
  rows=d.get("apps",d.get("addons")) if isinstance(d,dict) else d
  if r.get("result")!="ok" or not isinstance(rows,list):return None
  return sum(x.get("slug")==SLUG and x.get("installed") is not False
             for x in rows if isinstance(x,dict))
 except (TypeError,ValueError,AttributeError):return None
def registry_zero():
 # Reads only numeric integration count, not raw HA registry content.
 code=("import pathlib,json; "
  "p=pathlib.Path('/config/.storage/core.config_entries'); "
  "d=json.loads(p.read_text()).get('data',{}).get('entries',[]); "
  "print('JNS_CORE_AUTH_TARGET_COUNT='+str(sum("
  "isinstance(x,dict) and x.get('domain')=='esphome' for x in d)))")
 j=guest(["docker","exec","homeassistant","python3","-c",code],45)
 if not good(j):return False
 return "JNS_CORE_AUTH_TARGET_COUNT=0" in str(j.get("out-data",""))
def stage_source():
 files={}
 for n in FILES:
  p=ROOT/n
  if not p.is_file() or p.is_symlink() or p.stat().st_size>24000:
   raise RuntimeError("source_not_trusted")
  files[n]=p.read_bytes()
 if b"homeassistant_api: true" not in files["config.yaml"] or b"boot: manual_only" not in files["config.yaml"]:
  raise RuntimeError("manifest_permission_mismatch")
 if b"version: \"0.1.2\"" not in files["config.yaml"]:
  raise RuntimeError("unexpected_app_version")
 if not files["run.sh"].startswith(b"#!/command/with-contenv bashio\n"):
  raise RuntimeError("unexpected_launcher")
 if b"FROM ghcr.io/home-assistant/base-python:3.14-alpine3.24" not in files["Dockerfile"]:
  raise RuntimeError("unexpected_base_image")
 if not good(gsh("test -d "+shlex.quote(GUEST_ROOT)+" && test ! -e "+
             shlex.quote(FOLDER)+" && test ! -L "+shlex.quote(FOLDER),55)):
  raise RuntimeError("local_source_collision")
 buf=io.BytesIO()
 with tarfile.open(fileobj=buf,mode="w") as archive:
  for n,data in files.items():
   rec=tarfile.TarInfo(NAME+"/"+n)
   rec.size=len(data)
   rec.mode=0o600
   archive.addfile(rec,io.BytesIO(data))
 data=base64.b64encode(buf.getvalue()).decode("ascii")
 cmd="umask 077; printf '%s' "+shlex.quote(data)+" | base64 -d | tar -x -C "+shlex.quote(GUEST_ROOT)
 if not good(gsh(cmd,80)):raise RuntimeError("app_source_stage_failed")
 for n,data in files.items():
  target=shlex.quote(FOLDER+"/"+n)
  digest=hashlib.sha256(data).hexdigest()
  if not good(gsh("test ! -L "+target+" && test \"$(sha256sum "+target+
            " | cut -d' ' -f1)\" = "+shlex.quote(digest),35)):
   raise RuntimeError("app_source_checksum")
 note("SOURCE","fixed_public_files_hash_verified")
def store_prepare():
 j=guest(["ha","store","reload","--no-progress"],190)
 if not good(j):note("STORE","reload_cli_uncertain")
 else:note("STORE","reload_cli_exit_zero")
 j=guest(["ha","store","info",SLUG,"--no-progress","--raw-json"],65)
 if not good(j):raise RuntimeError("store_info_missing")
 try:
  doc=json.loads(j.get("out-data") or "{}")
  rows=doc.get("data",{}).get("addons",[])
  matches=[x for x in rows if isinstance(x,dict) and x.get("slug")==SLUG]
  if doc.get("result")!="ok" or len(matches)!=1:raise ValueError
  if str(matches[0].get("version_latest") or matches[0].get("version"))!="0.1.2":raise ValueError
 except (ValueError,TypeError,AttributeError):
  raise RuntimeError("store_app_version_not_indexed")
 note("STORE","app_v012_indexed")
def read_probe():
 for i in range(24):
  j=guest(["ha","apps","logs",SLUG,"--lines","70"],36)
  if good(j):
   lines=re.findall(r"JNS_HA905_CORE_AUTH_READONLY=(\{[^\r\n]*\})",str(j.get("out-data","")))
   for line in lines[-1:]:
    try:
     r=json.loads(line)
     if r.get("invalid_flow_post_sent") is not True or r.get("no_device_details_sent") is not True or r.get("used_security_output") is not False or r.get("logged_token") is not False:
      continue
     statuses=r.get("statuses")
     if not isinstance(statuses,dict) or set(statuses)!={"supervisor_info","core_root","core_config","rejected_flow_post","esphome_blank_flow_start","esphome_blank_flow_cancel","esphome_blank_form"}:continue
     form=statuses.get("esphome_blank_form")
     if not isinstance(form,bool):continue
     if any(v not in ALLOWED_STATUSES for k,v in statuses.items() if k!="esphome_blank_form"):continue
     note("HTTP_RESULT",json.dumps({"token_present":r.get("token_present") is True,"statuses":statuses},sort_keys=True))
     return statuses
    except (ValueError,TypeError):continue
  time.sleep(2)
 return None
def cleanup():
 # This slug is wholly dedicated to this one-time read-only diagnostic.
 # Treat uncertain uninstall as incomplete and preserve for explicit review.
 count=inventory()
 if count is None:
  note("CLEANUP","installed_inventory_unknown")
  return False
 if count>0:
  guest(["ha","apps","stop",SLUG,"--no-progress","--raw-json"],55)
  j=guest(["ha","apps","uninstall",SLUG,"--no-progress","--raw-json"],180)
  if not good(j):
   note("CLEANUP","uninstall_command_failed_or_unknown")
   return False
 for _ in range(24):
  count=inventory()
  if count==0:break
  time.sleep(3)
 if count!=0:
  note("CLEANUP","installed_app_removal_unverified")
  return False
 rm=("test -d "+shlex.quote(FOLDER)+" && test ! -L "+shlex.quote(FOLDER)
  +" && rm -f "+" ".join(shlex.quote(FOLDER+"/"+n) for n in FILES)
  +" && rmdir "+shlex.quote(FOLDER))
 if not good(gsh(rm,85)):
  note("CLEANUP","source_removal_unverified")
  return False
 note("CLEANUP","installed_app_absent_and_source_removed")
 return True
def main():
 if os.uname().nodename.split(".")[0]!="nodec":
  note("BLOCKED","wrong_gateway");return 1
 if not safe_owners():
  note("BLOCKED","source_or_target_not_running");return 1
 if pathlib.Path.home().joinpath(".local/share/jns-security-failback-20261028/state.json").exists():
  note("BLOCKED","security_handover_recovery_armed");return 1
 timer=shell("nodea",["systemctl","is-active","jns-ha906-recovery-20261028.timer"],22)
 if not timer or (timer.returncode==0 and timer.stdout.strip()=="active"):
  note("BLOCKED","nodea_recovery_timer_active_or_unknown");return 1
 if not registry_zero():
  note("BLOCKED","target_esphome_not_zero");return 1
 if inventory()!=0:
  note("BLOCKED","probe_app_installed_or_inventory_unknown");return 1
 if info() and info().get("installed") is not False:
  note("BLOCKED","probe_slug_collision");return 1
 done=False
 result=None
 try:
  stage_source()
  store_prepare()
  j=guest(["ha","apps","install",SLUG,"--no-progress","--raw-json"],215)
  if not good(j):raise RuntimeError("install_command_failure")
  if inventory()!=1:raise RuntimeError("installed_inventory_not_proven")
  v=info()
  if not v or v.get("repository")!="local" or v.get("version")!="0.1.2" or v.get("state")!="stopped":
   raise RuntimeError("app_not_stopped_after_install")
  note("INSTALLED","stopped_verified")
  if not safe_owners() or not registry_zero():raise RuntimeError("ownership_changed_before_start")
  j=guest(["ha","apps","start",SLUG,"--no-progress","--raw-json"],80)
  if not good(j):raise RuntimeError("start_unverified")
  result=read_probe()
  if result is None:raise RuntimeError("no_status_only_result")
 finally:
  done=cleanup()
 if not done or not safe_owners() or not registry_zero():
  note("BLOCKED","post_probe_cleanup_or_ownership");return 1
 if result is None:return 1
 # A malformed request must never be accepted. 400/422 confirms that
 # schema validation rejected the intentionally missing handler; 401/403
 # establishes authorization rejection. Other codes are diagnostic failures.
 if result.get("rejected_flow_post") not in (400,401,403,404,405,422):
  note("BLOCKED","schema_invalid_post_unexpected_status")
  return 1
 if result.get("esphome_blank_flow_cancel")!=200 or result.get("esphome_blank_form") is not True:
  note("BLOCKED","blank_esphome_flow_or_cleanup_not_proven")
  return 1
 note("RESULT","blank_esphome_form_created_and_cancelled_both_VMs_unchanged")
 return 0
if __name__=="__main__":
 try:sys.exit(main())
 except (OSError,RuntimeError,ValueError,TypeError) as ex:
  # The exception class and a hardcoded internal reason only, no CLI bodies.
  reason=str(ex) if isinstance(ex,RuntimeError) else type(ex).__name__
  safe=reason if re.fullmatch("[A-Za-z0-9_]{1,70}",reason) else "unclassified"
  note("BLOCKED",safe)
  sys.exit(1)
