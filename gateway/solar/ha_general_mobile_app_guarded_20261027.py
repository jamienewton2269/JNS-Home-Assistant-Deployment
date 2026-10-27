#!/usr/bin/env python3
"""Enable built-in Home Assistant mobile_app in HA-General VM905.
Guarded minimal change via Node C -> Node B QGA, exact private backup, Core check,
rollback on failed config check. Restart once and verify actual start time.
No secrets or configuration text logged. Source VM902 remains active.
"""
import base64,datetime,json,os,re,shlex,subprocess,sys,time
SSH=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=6"]
PATCH=r'''
import hashlib,json,os,pathlib,re,shutil,stat
root=pathlib.Path("/config")
p=root/"configuration.yaml"
if not p.is_file() or p.is_symlink():raise SystemExit(77)
old=p.read_bytes()
if not 10<len(old)<1024*1024:raise SystemExit(78)
text=old.decode("utf-8")
if re.search(r"(?m)^\s*default_config\s*:",text) or re.search(r"(?m)^mobile_app\s*:",text):
 print("JNS_MOBILE_APP_CONFIG=already_enabled")
else:
 folder=root/".jns_migration_backups"
 if folder.is_symlink():raise SystemExit(79)
 folder.mkdir(mode=0o700,exist_ok=True)
 folder.chmod(0o700)
 backup=folder/"mobile_app_prechange_20261027_configuration.yaml"
 if backup.exists() or backup.is_symlink():raise SystemExit(80)
 with backup.open("xb") as dest:
  dest.write(old)
  dest.flush()
  os.fsync(dest.fileno())
 backup.chmod(0o600)
 updated=old.rstrip(b"\r\n")+b"\n\n# JNS consolidation: Companion App mobile clients\nmobile_app:\n"
 tmp=p.with_name("configuration.yaml.jns-mobile-tmp")
 if tmp.exists() or tmp.is_symlink():raise SystemExit(81)
 with tmp.open("xb") as dest:
  dest.write(updated)
  dest.flush()
  os.fsync(dest.fileno())
 os.chmod(tmp,stat.S_IMODE(p.stat().st_mode))
 os.replace(tmp,p)
 print("JNS_MOBILE_APP_CONFIG=staged_with_private_backup")
'''
CHECK=r'''
import json,pathlib,re
p=pathlib.Path("/config/configuration.yaml")
if not p.is_file() or p.is_symlink():raise SystemExit(77)
t=p.read_text(errors="replace")
if not re.search(r"(?m)^mobile_app\s*:\s*$",t):raise SystemExit(78)
print("JNS_MOBILE_APP_CONFIG_PRESENT=yes")
'''
ROLLBACK=r'''
import os,pathlib
root=pathlib.Path("/config")
p=root/"configuration.yaml"
b=root/".jns_migration_backups/mobile_app_prechange_20261027_configuration.yaml"
if b.is_symlink() or not b.is_file() or p.is_symlink():raise SystemExit(79)
t=p.with_name("configuration.yaml.jns-rollback-tmp")
if t.exists():raise SystemExit(80)
with t.open("xb") as f:
 f.write(b.read_bytes());f.flush();os.fsync(f.fileno())
os.chmod(t,p.stat().st_mode&0o777)
os.replace(t,p)
print("JNS_MOBILE_APP_ROLLBACK=exact_private_backup_restored")
'''
def die(code):
 print("JNS_MOBILE_APP_BLOCKED="+code,flush=True)
 raise SystemExit(1)
def run(cmd,timeout=27):
 try:return subprocess.run(cmd,capture_output=True,text=True,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):return None
def ssh(node,args,timeout=30):
 p=run(SSH+[node,shlex.join(args)],timeout)
 return p.stdout if p and p.returncode==0 else None
def guest(args,timeout=120):
 s=ssh("nodeb",["qm","guest","exec","905","--",*args],35)
 if not s:return None
 try:j=json.loads(s)
 except ValueError:return None
 deadline=time.monotonic()+timeout
 while time.monotonic()<deadline:
  if j.get("exited"):return j
  if not j.get("pid"):break
  time.sleep(.7)
  s=ssh("nodeb",["qm","guest","exec-status","905",str(j["pid"])],21)
  if not s:break
  try:j=json.loads(s)
  except ValueError:break
 return None
def code_run(code):
 b=base64.b64encode(code.encode()).decode()
 return guest(["docker","exec","homeassistant","python3","-c",
               "exec(__import__('base64').b64decode('"+b+"'))"],65)
def core_start():
 x=guest(["docker","inspect","homeassistant","--format","{{.State.StartedAt}}"],38)
 if x and x.get("exitcode")==0:return (x.get("out-data") or "").strip()
 return None
def timestamp(x):
 try:return datetime.datetime.fromisoformat(x.replace("Z","+00:00"))
 except (ValueError,AttributeError):return None
def archive_gates():
 code=r'''
import json,pathlib
p=pathlib.Path("/mnt/pve/NAS/dump")
try:
 a=json.loads((p/"jns-ha-general-consolidation-20261027-v1/MANIFEST.json").read_text())
 b=json.loads((p/"jns-vm902-consolidation-20261027-v1/MANIFEST.json").read_text())
 ok=a.get("vm")==905 and a.get("zstd_test_passed") and b.get("source_node")=="nodea"
except (OSError,ValueError):ok=False
print("JNS_MOBILE_ARCHIVE_GATES="+("yes" if ok else "no"))
'''
 q=base64.b64encode(code.encode()).decode()
 out=ssh("nodeb",["python3","-c","exec(__import__('base64').b64decode('"+q+"'))"],25)
 return bool(out and "JNS_MOBILE_ARCHIVE_GATES=yes" in out)
def main():
 if os.uname().nodename.split(".")[0]!="nodec":die("wrong_runner")
 for node,vm in (("nodea",902),("nodeb",905)):
  state=ssh(node,["qm","status",str(vm)])
  if not state or state.strip()!="status: running":die("source_or_target_not_running")
 conf=ssh("nodeb",["qm","config","905"]) or ""
 if not re.search(r"^name:\s*ha-s2-general\s*$",conf,re.M) or not re.search(r"^memory:\s*2048\s*$",conf,re.M):
  die("target_identity_or_ram_not_ready")
 if not archive_gates():die("offhost_archive_markers_missing")
 old_start=timestamp(core_start())
 if not old_start:die("current_core_start_unknown")
 res=code_run(PATCH)
 if not res or res.get("exitcode")!=0:die("target_config_patch_failed")
 status=[x for x in (res.get("out-data") or "").splitlines() if x.startswith("JNS_MOBILE_APP_CONFIG=")]
 if len(status)!=1:die("missing_patch_receipt")
 print(status[0],flush=True)
 if status[0].endswith("already_enabled"):
  print("JNS_MOBILE_APP_ALREADY_CONFIGURED=yes",flush=True)
  return 0
 test=guest(["ha","core","check"],230)
 if not test or test.get("exitcode")!=0:
  rb=code_run(ROLLBACK)
  print("JNS_MOBILE_APP_ROLLBACK="+("successful" if rb and rb.get("exitcode")==0 else "needs_manual_attention"),flush=True)
  die("homeassistant_config_check_failed")
 print("JNS_MOBILE_APP_CONFIG_CHECK=passed",flush=True)
 cmd=guest(["ha","core","restart"],90)
 # On HAOS, CLI may report an error because Core disconnects while restarting.
 # Treat command outcome as ambiguous; verify runtime start and health before judging.
 if not cmd or cmd.get("exitcode")!=0:
  print("JNS_MOBILE_APP_RESTART_COMMAND=ambiguous_verifying_runtime",flush=True)
 else:print("JNS_MOBILE_APP_RESTART_COMMAND=accepted",flush=True)
 deadline=time.monotonic()+225
 while time.monotonic()<deadline:
  started=timestamp(core_start())
  if started and started>old_start:
   chk=code_run(CHECK)
   if chk and chk.get("exitcode")==0:
    info=guest(["ha","core","info"],55)
    if info and info.get("exitcode")==0:
     print("JNS_MOBILE_APP_ENABLE_RESULT="+json.dumps({"yaml_configured":True,
        "core_started_after_change":True,"core_running":True,
        "vm905_shutdown":False,"vm902_source_unchanged":True,
        "new_companion_devices_registered":False,
        "user_phone_registration_required":True},sort_keys=True),flush=True)
     return 0
  time.sleep(5)
 die("postrestart_health_unverified")
if __name__=="__main__":main()
