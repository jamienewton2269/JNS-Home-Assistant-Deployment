#!/usr/bin/env python3
"""One-time user-authorised JNS HA905 Core API permission probe.

Only the reviewed temporary app is installed. Source VM906 must stay running.
No Home Assistant Core restart, ESPHome enrollment, config-flow writes, security
device control, or VM power changes. Fail closed for collisions and always
attempt removal. Scrub all CLI/app logs except the fixed probe's status JSON.
"""
import base64, hashlib, json, os, pathlib, shlex, subprocess, sys
SOURCE=pathlib.Path(__file__).parent/"ha905_core_api_bridge_app"
FILES=("config.yaml","Dockerfile","probe.py","run.sh")
SHELL=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=6"]
REMOTE=r'''
import base64, hashlib, io, json, os, pathlib, re, subprocess, sys, tarfile, time
SLUG="local_jns_ha905_core_api_probe"
NAME="jns_ha905_core_api_probe"
BASE="/mnt/data/supervisor/apps/local"
TARGET=BASE+"/"+NAME

def status(key,value):
 print("JNS_HA905_API_ONCE_"+key+"="+str(value),flush=True)
def fail(key):
 status("BLOCKED",key)
 raise SystemExit(80)
if os.geteuid()!=0 or os.uname().nodename.split(".")[0]!="nodeb":
 fail("host_identity")
def host_cmd(args,timeout=25):
 try:return subprocess.run(args,text=True,capture_output=True,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):return None
def qga(args,timeout=180):
 r=host_cmd(["qm","guest","exec","905","--",*args],30)
 if not r or r.returncode: return None
 try:j=json.loads(r.stdout)
 except ValueError:return None
 until=time.monotonic()+timeout
 while time.monotonic()<until and not j.get("exited"):
  if not j.get("pid"):return None
  time.sleep(1)
  r=host_cmd(["qm","guest","exec-status","905",str(j["pid"])],25)
  if not r or r.returncode:return None
  try:j=json.loads(r.stdout)
  except ValueError:return None
 return j if j.get("exited") and not j.get("out-truncated") else None
def script(cmd,timeout=120):
 return qga(["sh","-c",cmd],timeout)
def success(j):
 return bool(j and j.get("exitcode")==0)
def guest_fixed(cmd,timeout=120):
 j=script(cmd,timeout)
 return success(j),str(j.get("out-data","")) if j else ""
target_state=host_cmd(["qm","status","905"])
if not target_state or target_state.returncode or target_state.stdout.strip()!="status: running":
 fail("target_offline")
backup=pathlib.Path("/mnt/pve/NAS/dump/jns-ha-general-consolidation-20261027-v1/MANIFEST.json")
if not backup.is_file() or backup.is_symlink():fail("backup_manifest_missing")
try:
 if not isinstance(json.loads(backup.read_text()),dict):fail("backup_manifest_unparseable")
except (OSError,ValueError,TypeError):fail("backup_manifest_unparseable")
root=pathlib.Path("/var/lib/jns-solar/consolidation/ha905-core-api-bridge-probe-20261028-v1")
manifest=root/"manifest.json"
if root.is_symlink() or not manifest.is_file() or manifest.is_symlink():fail("private_stage_missing")
try:
 stage=json.loads(manifest.read_text())
 if stage.get("target_vm")!=905 or stage.get("app_installed") is not False:fail("wrong_stage_identity")
except (OSError,ValueError,TypeError):fail("invalid_stage")
payload=json.loads(sys.stdin.buffer.read(120000))
if payload.get("commit")!="0518305e69b5fdc18db77e93b026e724dab9fd53":fail("unexpected_source_commit")
items=payload.get("files")
if not isinstance(items,dict) or set(items)!=set(["config.yaml","Dockerfile","probe.py","run.sh"]):
 fail("unexpected_files")
files={}
for name,record in items.items():
 try:
  raw=base64.b64decode(record["data"],validate=True)
  if hashlib.sha256(raw).hexdigest()!=record["sha256"]:fail("source_checksum")
  if len(raw)>20000:fail("source_size")
  files[name]=raw
 except (ValueError,TypeError,KeyError):fail("invalid_file")
if b"FROM ghcr.io/home-assistant/base:3.24\n" not in files["Dockerfile"]:fail("image_pin")
if b"homeassistant_api: true" not in files["config.yaml"]:fail("api_manifest")
if b"boot: manual_only" not in files["config.yaml"]:fail("manual_boot")
if not files["run.sh"].startswith(b"#!/command/with-contenv bashio\n"):fail("token_env")
if b"method=\"GET\"" not in files["probe.py"] or b"method=\"POST\"" in files["probe.py"]:
 fail("probe_policy")
# The source operator must retain security ownership throughout the probe.
# The Node C launcher checks VM906; there is no interaction with it in this transaction.
g=script('test -d /mnt/data/supervisor && command -v base64 >/dev/null && command -v tar >/dev/null && command -v sha256sum >/dev/null && ha apps --help >/dev/null 2>&1',35)
if not success(g):fail("guest_prerequisites")
g=script('test ! -e '+TARGET+' && test ! -L '+TARGET,25)
if not success(g):fail("app_folder_collision")
g=script('ha apps info '+SLUG+' --raw-json >/dev/null 2>&1',30)
if success(g):fail("installed_slug_collision")
status("PRECHECK","passed")
bundle=io.BytesIO()
with tarfile.open(fileobj=bundle,mode="w") as tar:
 for name,data in files.items():
  info=tarfile.TarInfo(NAME+"/"+name)
  info.size=len(data);info.mode=0o600
  tar.addfile(info,io.BytesIO(data))
encoded=base64.b64encode(bundle.getvalue()).decode()
# One bounded app source extraction; no shell interpolation from repo data.
cmd="umask 077; mkdir -p "+BASE+" && printf '%s' '"+encoded+"' | base64 -d | tar -x -C "+BASE
g=script(cmd,45)
if not success(g):fail("copy_source_failed")
checks=" && ".join("test \"$(sha256sum "+TARGET+"/"+name+" | cut -d' ' -f1)\" = '"+hashlib.sha256(data).hexdigest()+"'"
 for name,data in files.items())
g=script(checks,45)
if not success(g):fail("guest_hash_mismatch")
status("SOURCE","verified")
installed=False
start_requested=False
confirmed=False
cleanup=False
try:
 # A store reload only indexes local app manifests; no Home Assistant Core restart.
 ok,_=guest_fixed("ha store reload --no-progress >/dev/null 2>&1",130)
 if not ok:
  ok,_=guest_fixed("ha store reload >/dev/null 2>&1",130)
 if not ok:fail("store_reload_failed")
 status("STORE","refreshed")
 ok,_=guest_fixed("ha apps install "+SLUG+" --no-progress >/dev/null 2>&1",360)
 if not ok:
  # CLI --no-progress may only be a global flag; retry only if not installed.
  g=script("ha apps info "+SLUG+" --raw-json",35)
  if not success(g):fail("install_not_registered")
  try:
   info=json.loads(g.get("out-data") or "{}")
   obj=info.get("data",info) if isinstance(info,dict) else {}
   if not isinstance(obj,dict) or not obj.get("installed"):fail("install_not_confirmed")
  except (ValueError,TypeError):fail("install_info_invalid")
 installed=True
 status("INSTALL","registered")
 # Verify the app hasn't unexpectedly started before the single explicit start.
 g=script("ha apps info "+SLUG+" --raw-json",35)
 if not success(g):fail("post_install_info_failed")
 try:
  info=json.loads(g.get("out-data") or "{}")
  obj=info.get("data",info) if isinstance(info,dict) else {}
  if not isinstance(obj,dict) or not obj.get("installed"):fail("post_install_not_installed")
  if str(obj.get("state","")).lower() in ("started","running"):fail("unexpected_autostart")
 except (ValueError,TypeError):fail("post_install_invalid_json")
 start_requested=True
 status("START_REQUESTS","1")
 # The app is a one-shot and may exit before CLI returns.
 r=script("ha apps start "+SLUG+" >/dev/null 2>&1; echo JNS_HA905_START_DONE",80)
 status("START_CLI_FINISHED",bool(r and "JNS_HA905_START_DONE" in str(r.get("out-data",""))))
 for _ in range(12):
  time.sleep(1.5)
  g=script("ha apps logs "+SLUG+" --lines 100",30)
  if not g:continue
  output=str(g.get("out-data",""))
  markers=re.findall(r"JNS_HA905_TRUSTED_APP_CORE_PREFLIGHT=(\{[^\r\n]*\})",output)
  if not markers:continue
  try:
   obj=json.loads(markers[-1])
  except ValueError:continue
  status("CORE_ROOT_HTTP",obj.get("core_root_http","unknown"))
  status("CORE_CONFIG_HTTP",obj.get("core_config_http","unknown"))
  confirmed=(obj.get("core_root_http")==200 and obj.get("core_config_http")==200
             and obj.get("read_only") is True and obj.get("esphome_enrolled") is False)
  break
 status("AUTH_SUCCESS",str(confirmed).lower())
finally:
 # No admin-capable installed app must be left behind by this one-shot operation.
 # Existing slug was absent, so only remove our own new install and source.
 if installed:
  guest_fixed("ha apps stop "+SLUG+" >/dev/null 2>&1 || true",35)
  guest_fixed("ha apps uninstall "+SLUG+" >/dev/null 2>&1",155)
  g=script("ha apps info "+SLUG+" --raw-json",25)
  if success(g):
   try:
    j=json.loads(g.get("out-data") or "{}")
    o=j.get("data",j) if isinstance(j,dict) else {}
    cleanup=bool(isinstance(o,dict) and not o.get("installed"))
   except (ValueError,TypeError):cleanup=False
  else:cleanup=True
 else:cleanup=True
 if cleanup:
  g=script("rm -f "+TARGET+"/config.yaml "+TARGET+"/Dockerfile "+TARGET+"/probe.py "+TARGET+"/run.sh && rmdir "+TARGET+" && ha store reload >/dev/null 2>&1",120)
  cleanup=cleanup and success(g)
 status("INSTALLED_APP_REMOVED",str(cleanup).lower())
 status("VM906_CONTROL_UNCHANGED","yes")
if not confirmed or not cleanup:raise SystemExit(81)
status("RESULT","verified_read_only_get_200")
'''.strip()

def ssh(node,args,stdin=None,timeout=700):
 try:return subprocess.run(SHELL+[node,shlex.join(args)],input=stdin,text=True,
                           capture_output=True,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):return None

def main():
 if os.uname().nodename.split(".")[0]!="nodec":
  print("JNS_API_ONCE_BLOCKED=runner_identity");return 1
 s=ssh("nodea",["qm","status","906"],timeout=18)
 if not s or s.returncode or s.stdout.strip()!="status: running":
  print("JNS_API_ONCE_BLOCKED=VM906_not_running");return 1
 for node,vm in (("nodeb",905),("nodea",902)):
  s=ssh(node,["qm","status",str(vm)],timeout=18)
  if not s or s.returncode or s.stdout.strip()!="status: running":
   print("JNS_API_ONCE_BLOCKED=required_VM_offline");return 1
 record={}
 for name in FILES:
  p=SOURCE/name
  if not p.is_file() or p.is_symlink():
   print("JNS_API_ONCE_BLOCKED=untrusted_source");return 1
  b=p.read_bytes()
  record[name]={"data":base64.b64encode(b).decode(),"sha256":hashlib.sha256(b).hexdigest()}
 payload=json.dumps({"commit":"0518305e69b5fdc18db77e93b026e724dab9fd53","files":record})
 remote=base64.b64encode(REMOTE.encode()).decode()
 r=ssh("nodeb",["python3","-u","-c",
     "exec(__import__('base64').b64decode('"+remote+"'))"],payload,timeout=730)
 if not r:
  print("JNS_API_ONCE_BLOCKED=nodeb_timeout_or_transport");return 1
 allowed=("JNS_HA905_API_ONCE_",)
 lines=[x for x in r.stdout.splitlines() if x.startswith(allowed)]
 for x in lines:print(x,flush=True)
 if r.returncode!=0 or not any(x.endswith("RESULT=verified_read_only_get_200") for x in lines):
  print("JNS_API_ONCE_BLOCKED=non_successful_probe_or_cleanup");return 1
 s=ssh("nodea",["qm","status","906"],timeout=18)
 if not s or s.returncode or s.stdout.strip()!="status: running":
  print("JNS_API_ONCE_BLOCKED=source_state_changed_after_probe");return 1
 print("JNS_API_ONCE_NO_ESPHOME_OR_SECURITY_CUTOVER=yes")
 return 0
if __name__=="__main__":sys.exit(main())
