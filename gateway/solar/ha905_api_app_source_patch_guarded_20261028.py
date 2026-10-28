#!/usr/bin/env python3
"""Replace only the failed local-app Dockerfile with the tested Python-base one.

The app remains UNINSTALLED. The source is preserved for a later guarded run.
Requires expected original content, exact updated file checksum, and running
source HA-Security VM906. Never reads credentials or starts/stops any app/VM.
"""
import base64,hashlib,json,os,pathlib,shlex,subprocess,time
SOURCE=pathlib.Path(__file__).parent/"ha905_core_api_bridge_app/Dockerfile"
OLD_SHA="8ec11950722f51a64a63448d7148e784dc9cb17486c757cf43e8113a7fb1ef6e"
NEW_SHA="b9ec7544eea8686f0a64f45945aed6f93c295ea82ea78c7efd3bcdc9dcbc1db3"
SSH=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=6"]
HOST=r'''
import base64,hashlib,json,os,subprocess,time
if os.geteuid()!=0 or os.uname().nodename.split(".")[0]!="nodeb":raise SystemExit(70)
expected_old="8ec11950722f51a64a63448d7148e784dc9cb17486c757cf43e8113a7fb1ef6e"
expected_new="b9ec7544eea8686f0a64f45945aed6f93c295ea82ea78c7efd3bcdc9dcbc1db3"
target="/mnt/data/supervisor/apps/local/jns_ha905_core_api_probe/Dockerfile"
def guest(command,timeout=50):
 q=subprocess.run(["qm","guest","exec","905","--","sh","-c",command],
                  capture_output=True,text=True,timeout=25)
 if q.returncode:raise SystemExit(71)
 j=json.loads(q.stdout)
 deadline=time.monotonic()+timeout
 while not j.get("exited") and time.monotonic()<deadline:
  if not j.get("pid"):raise SystemExit(72)
  time.sleep(.5)
  p=subprocess.run(["qm","guest","exec-status","905",str(j["pid"])],
                    capture_output=True,text=True,timeout=25)
  if p.returncode:raise SystemExit(73)
  j=json.loads(p.stdout)
 return j
def ok(command):
 j=guest(command)
 return j.get("exited") and j.get("exitcode")==0
if not ok("test -f "+target+" && test ! -L "+target+" && test -d /mnt/data/supervisor/apps/local/jns_ha905_core_api_probe"):
 raise SystemExit(74)
if not ok("test \"$(sha256sum "+target+" | cut -d' ' -f1)\" = '"+expected_old+"'"):
 raise SystemExit(75)
raw=base64.b64decode(__import__("sys").stdin.read(10000).strip(),validate=True)
if hashlib.sha256(raw).hexdigest()!=expected_new:raise SystemExit(76)
# App must not be installed. JSON may return CLI exit 0 with result:error.
info=guest("ha apps info local_jns_ha905_core_api_probe --raw-json",40)
try:
 response=json.loads(info.get("out-data") or "{}")
 if response.get("result")!="ok":raise ValueError("store-entry-unavailable")
 item=response.get("data",{})
 if not isinstance(item,dict) or item.get("installed") is not False:
  raise ValueError("unexpected-installed-state")
except (ValueError,TypeError):raise SystemExit(77)
payload=base64.b64encode(raw).decode()
tmp=target+".jns-new"
if not ok("test ! -e "+tmp+" && test ! -L "+tmp):raise SystemExit(78)
cmd=("umask 077; printf '%s' '"+payload+"' | base64 -d > "+tmp+
     " && test \"$(sha256sum "+tmp+" | cut -d' ' -f1)\" = '"+expected_new+"'"+
     " && mv "+tmp+" "+target)
if not ok(cmd):raise SystemExit(79)
if not ok("test \"$(sha256sum "+target+" | cut -d' ' -f1)\" = '"+expected_new+"'"):
 raise SystemExit(80)
print("JNS_HA905_PYTHON_BASE_SOURCE_PATCH="+json.dumps({
 "source_only":True,"new_dockerfile_sha256_verified":True,
 "app_started":False,"app_installed":False,"ha_core_restarted":False,
 "esphome_changed":False,"vm906_changed":False},sort_keys=True))
'''
def ssh(node,args,stdin=None,timeout=80):
 try:return subprocess.run(SSH+[node,shlex.join(args)],capture_output=True,
                           text=True,input=stdin,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):return None
def main():
 if os.uname().nodename.split(".")[0]!="nodec":
  print("JNS_HA905_APP_SOURCE_PATCH_BLOCKED=wrong_runner");return 1
 for host,vm in (("nodea",906),("nodeb",905)):
  s=ssh(host,["qm","status",str(vm)],timeout=18)
  if not s or s.returncode or s.stdout.strip()!="status: running":
   print("JNS_HA905_APP_SOURCE_PATCH_BLOCKED=required_VM_offline");return 1
 data=SOURCE.read_bytes()
 if hashlib.sha256(data).hexdigest()!=NEW_SHA:
  print("JNS_HA905_APP_SOURCE_PATCH_BLOCKED=unreviewed_dockerfile");return 1
 code=base64.b64encode(HOST.encode()).decode()
 p=ssh("nodeb",["python3","-c","exec(__import__('base64').b64decode('"+code+"'))"],
       stdin=base64.b64encode(data).decode(),timeout=125)
 if not p or p.returncode:
  print("JNS_HA905_APP_SOURCE_PATCH_BLOCKED=target_validation");return 1
 rows=[s for s in p.stdout.splitlines() if s.startswith("JNS_HA905_PYTHON_BASE_SOURCE_PATCH=")]
 if len(rows)!=1:
  print("JNS_HA905_APP_SOURCE_PATCH_BLOCKED=no_confirmation");return 1
 print(rows[0],flush=True)
 print("JNS_HA905_APP_SOURCE_PATCH_VM906_UNCHANGED=yes",flush=True)
 return 0
if __name__=="__main__":raise SystemExit(main())
