#!/usr/bin/env python3
"""Guarded selective HA906->HA905 passive helper import, with config check and rollback.
Only input_boolean/input_number/input_select/input_text from staged packages.
No security automations, scripts, ESPHome or alarm_controller are imported here.
No HA restarts, ownership changes, guest power actions, network writes or secrets in CI.
"""
import base64,hashlib,json,os,re,shlex,subprocess,sys,time
SSH=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=6"]
SOURCE=r'''
import base64,hashlib,json,os,pathlib,re,sys
from collections import Counter
stage=pathlib.Path("/var/lib/jns-solar/consolidation/ha-security-906-20261027-v1")
mf=stage/"manifest.json"
allowed=("input_boolean","input_number","input_select","input_text")
if os.geteuid()!=0 or os.uname().nodename.split(".")[0]!="nodeb":raise SystemExit(72)
if not mf.is_file() or mf.is_symlink():raise SystemExit(73)
m=json.loads(mf.read_text())
if m.get("source_vm")!=906 or m.get("target_vm")!=905 or not m.get("stage_inert"):raise SystemExit(74)
sections={}
for info in m.get("files",[]):
 if info.get("kind")!="package":continue
 p=stage/"files"/str(info.get("staged_basename",""))
 if p.is_symlink() or not p.is_file():raise SystemExit(75)
 b=p.read_bytes()
 if hashlib.sha256(b).hexdigest()!=info.get("sha256"):raise SystemExit(76)
 t=b.decode("utf-8")
 markers=list(re.finditer(r"(?m)^([a-z][a-z0-9_]*)\s*:",t))
 for n,marker in enumerate(markers):
  key=marker.group(1)
  if key not in allowed:continue
  begin=marker.start()
  end=markers[n+1].start() if n+1<len(markers) else len(t)
  if key in sections:raise SystemExit(77)
  sections[key]=t[begin:end].rstrip()+"\n"
if not all(k in sections for k in allowed):raise SystemExit(78)
body="# JNS Security passive helper definitions only; no automations or alarm ownership.\n"
body+="# Generated from verified, isolated VM906 staging; do not hand-edit.\n\n"
for key in allowed:body+=sections[key]+"\n"
if len(body)>180000:raise SystemExit(79)
print("JNS_PRIVATE_HELPER_PAYLOAD="+base64.b64encode(body.encode()).decode())
'''
TARGET=r'''
import base64,hashlib,json,os,pathlib,re,sys
path=pathlib.Path("/config/packages/jns_ha_security_passive_helpers_20261027.yaml")
def fail(s):
 print("JNS_HELPER_IMPORT_BLOCKED="+s)
 raise SystemExit(79)
if len(sys.argv)!=2:fail("invalid_args")
try:data=base64.b64decode(sys.argv[1],validate=True)
except (ValueError,TypeError):fail("invalid_payload")
if len(data)>180000 or not data:fail("size_invalid")
text=data.decode("utf-8")
expected=("input_boolean","input_number","input_select","input_text")
sections=re.findall(r"(?m)^([a-z][a-z0-9_]*)\s*:",text)
if sorted(sections)!=sorted(expected):fail("unexpected_top_level_sections")
if path.exists() or path.is_symlink():fail("target_exists")
if not path.parent.is_dir() or path.parent.is_symlink():fail("package_directory_missing")
# Guard against collision with native and UI-created entities in live HA905 registry.
try:
 registry=json.loads(pathlib.Path("/config/.storage/core.entity_registry").read_text())
 ids={x.get("entity_id") for x in registry.get("data",{}).get("entities",[]) if isinstance(x,dict)}
except (OSError,ValueError):fail("entity_registry_unreadable")
parent=None;new=set();total=0
for line in text.splitlines():
 m=re.match(r"^([a-z][a-z0-9_]*)\s*:",line)
 if m:
  parent=m.group(1);continue
 if parent in expected:
  match=re.match(r"^  ([a-zA-Z][a-zA-Z0-9_]*)\s*:",line)
  if match:
   eid=parent+"."+match.group(1)
   if eid in ids or eid in new:fail("helper_id_collision")
   new.add(eid);total+=1
if total<100 or total>250:fail("helper_count_unexpected")
temp=path.with_suffix(".yaml.jns-tmp")
if temp.exists() or temp.is_symlink():fail("temp_already_exists")
flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL
with os.fdopen(os.open(str(temp),flags,0o600),"wb") as f:
 f.write(data)
 f.flush()
 os.fsync(f.fileno())
temp.replace(path)
path.chmod(0o600)
print("JNS_HELPER_IMPORT_STAGED="+json.dumps({"passive_helper_definitions":total,
 "yaml_sections":list(expected),"active_automations_added":0,
 "core_restart_performed":False,"config_check_pending":True},sort_keys=True))
'''
ROLLBACK=r'''
import hashlib,pathlib,sys
p=pathlib.Path("/config/packages/jns_ha_security_passive_helpers_20261027.yaml")
if p.is_symlink():raise SystemExit(71)
if p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest()==sys.argv[1]:
 p.unlink()
 print("JNS_HELPER_IMPORT_ROLLBACK=verified_file_removed")
else:
 print("JNS_HELPER_IMPORT_ROLLBACK=manual_attention")
 raise SystemExit(72)
'''
def ssh(host,args,timeout=30):
 try:return subprocess.run(SSH+[host,shlex.join(args)],capture_output=True,text=True,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):return None
def guest(args,timeout=90):
 q=ssh("nodeb",["qm","guest","exec","905","--",*args],min(timeout,55))
 if not q or q.returncode:return None
 try:j=json.loads(q.stdout)
 except ValueError:return None
 for _ in range(70):
  if j.get("exited"):return j
  if not j.get("pid"):return None
  time.sleep(.6)
  q=ssh("nodeb",["qm","guest","exec-status","905",str(j["pid"])],25)
  if not q or q.returncode:return None
  try:j=json.loads(q.stdout)
  except ValueError:return None
 return None
def main():
 if os.uname().nodename.split(".")[0]!="nodec":
  print("JNS_HELPER_IMPORT_BLOCKED=wrong_runner");return 1
 for node,vm,name in (("nodea",906,"ha-security"),("nodeb",905,"ha-s2-general")):
  p=ssh(node,["qm","status",str(vm)])
  if not p or p.returncode or p.stdout.strip()!="status: running":
   print("JNS_HELPER_IMPORT_BLOCKED=source_or_target_unavailable");return 1
 src=base64.b64encode(SOURCE.encode()).decode()
 r=ssh("nodeb",["python3","-c","exec(__import__('base64').b64decode('"+src+"'))"],timeout=40)
 if not r or r.returncode:
  print("JNS_HELPER_IMPORT_BLOCKED=staging_unavailable");return 1
 lines=[x.split("=",1)[1] for x in r.stdout.splitlines() if x.startswith("JNS_PRIVATE_HELPER_PAYLOAD=")]
 if len(lines)!=1:
  print("JNS_HELPER_IMPORT_BLOCKED=invalid_stage_output");return 1
 try:payload=base64.b64decode(lines[0],validate=True)
 except ValueError:
  print("JNS_HELPER_IMPORT_BLOCKED=invalid_payload");return 1
 digest=hashlib.sha256(payload).hexdigest()
 if len(payload)>180000:return 1
 b64=base64.b64encode(TARGET.encode()).decode()
 result=guest(["docker","exec","homeassistant","python3","-c",
  "exec(__import__('base64').b64decode('"+b64+"'))",lines[0]],timeout=100)
 if not result or result.get("exitcode")!=0:
  print("JNS_HELPER_IMPORT_BLOCKED=target_writer_or_collision_gate");return 1
 if "JNS_HELPER_IMPORT_STAGED=" not in str(result.get("out-data","")):
  print("JNS_HELPER_IMPORT_BLOCKED=target_confirmation_missing");return 1
 print([x for x in str(result["out-data"]).splitlines() if x.startswith("JNS_HELPER_IMPORT_STAGED=")][-1],flush=True)
 # HAOS native config validation without restarting Core.
 check=guest(["ha","core","check"],timeout=250)
 if check and check.get("exitcode")==0:
  print("JNS_HELPER_IMPORT_CONFIGCHECK=passed",flush=True)
  print("JNS_HELPER_IMPORT_PENDING_CORE_RESTART=yes",flush=True)
  return 0
 print("JNS_HELPER_IMPORT_CONFIGCHECK=failed_rolling_back",flush=True)
 code=base64.b64encode(ROLLBACK.encode()).decode()
 rb=guest(["docker","exec","homeassistant","python3","-c",
     "exec(__import__('base64').b64decode('"+code+"'))",digest],timeout=60)
 if rb and rb.get("exitcode")==0 and "verified_file_removed" in str(rb.get("out-data","")):
  print("JNS_HELPER_IMPORT_ROLLBACK=successful",flush=True)
 else:
  print("JNS_HELPER_IMPORT_ROLLBACK=manual_attention",flush=True)
 return 1
if __name__=="__main__":sys.exit(main())
