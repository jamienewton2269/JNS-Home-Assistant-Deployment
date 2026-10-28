#!/usr/bin/env python3
"""Guarded private staging of native VM906 manual alarm + scripts + templates +
six DISABLED automations on VM905. Does not restart Core or control hardware.
Source secrets are transferred privately through Node C using QGA, never logged.
Back up target secrets.yaml with byte-for-byte private rollback; on Core config
check failure rollback both staged package and secrets file. Fail closed.
"""
import base64,json,os,re,shlex,subprocess,sys,time
SSH=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=6"]
SOURCE=r'''
import json,hashlib,os,pathlib,re,sys,base64
p=pathlib.Path("/var/lib/jns-solar/consolidation/ha-security-906-20261027-v1")
m=json.loads((p/"manifest.json").read_text())
if os.geteuid()!=0 or os.uname().nodename.split(".")[0]!="nodeb":raise SystemExit(70)
if m.get("source_vm")!=906 or m.get("target_vm")!=905:raise SystemExit(71)
def parts(s):
 markers=list(re.finditer(r"(?m)^([a-z][a-z0-9_]*)\s*:\s*(?:#.*)?$",s))
 return [(x.group(1),s[x.end():markers[i+1].start() if i+1<len(markers) else len(s)])
         for i,x in enumerate(markers)]
main=None;automations=[];templates=[];scripts=[]
for row in m["files"]:
 f=p/"files"/row["staged_basename"]
 if f.is_symlink() or not f.is_file():raise SystemExit(72)
 b=f.read_bytes()
 if hashlib.sha256(b).hexdigest()!=row["sha256"]:raise SystemExit(73)
 if row["original_basename"]=="configuration.yaml":
  main=dict(parts(b.decode())).get("alarm_control_panel")
 if row["kind"]=="package":
  for key,frag in parts(b.decode()):
   if key=="automation":automations.append(frag)
   if key=="template":templates.append(frag)
   if key=="script":scripts.append(frag)
if not main or not re.search(r"(?m)^\s*-\s*platform\s*:\s*manual\s*$",main):raise SystemExit(74)
keys=re.findall(r"!secret\s+([A-Za-z0-9_.-]+)",main)
if len(keys)!=1:raise SystemExit(75)
if len(automations)!=2 or sum(len(re.findall(r"(?m)^\s*-\s+id\s*:",frag)) for frag in automations)!=6:raise SystemExit(76)
if len(templates)!=1 or len(scripts)!=1:raise SystemExit(77)
# Prefix retained YAML with deterministic source provenance and first-run-disabled automations.
body="# JNS migrated native HA-Security configuration: passive until deliberate handover\n"
body+="# Source: VM906 verified private YAML staging; six automations initial_state:false\n"
body+="alarm_control_panel:\n"+main.rstrip()+"\n\n"
body+="automation:\n"
for fragment in automations:
 fragment=fragment.rstrip()
 lines=fragment.splitlines()
 # YAML permits indentless sequences under an individual mapping key; when
 # merging two such sequences, normalise them to a two-space list indent.
 id_indents=[len(x)-len(x.lstrip(" ")) for x in lines if re.match(r"^\s*-\s+id\s*:",x)]
 if not id_indents:raise SystemExit(79)
 if min(id_indents)==0:
  lines=[("  "+x if x.strip() else x) for x in lines]
 for line in lines:
  m=re.match(r"^(\s*)-\s+id\s*:",line)
  if m:
   body+=line+"\n"+m.group(1)+"  initial_state: false\n"
  else:body+=line+"\n"
body+="\nscript:\n"+scripts[0].rstrip()+"\n\n"
body+="template:\n"+templates[0].rstrip()+"\n"
if len(body)>210000:raise SystemExit(78)
print("JNS_PRIVATE_NATIVE_STAGE="+base64.b64encode(json.dumps({"yaml":body,"secret_ref":keys[0]}).encode()).decode())
'''
SECRETS=r'''
import base64,json,pathlib,sys,yaml
name=sys.argv[1]
p=pathlib.Path("/config/secrets.yaml")
if not p.is_file() or p.is_symlink():raise SystemExit(70)
data=yaml.safe_load(p.read_text()) or {}
if not isinstance(data,dict) or name not in data:raise SystemExit(71)
value=data[name]
if not isinstance(value,(str,int)):raise SystemExit(72)
print("JNS_PRIVATE_ALARM_SECRET="+base64.b64encode(json.dumps({"name":name,"value":str(value)}).encode()).decode())
'''
TARGET=r'''
import base64,json,os,pathlib,re,sys
from pathlib import Path
import yaml
root=Path("/config")
dest=root/"packages/jns_ha_security_native_cutover_20261028_v2.yaml"
secrets=root/"secrets.yaml"
backup=root/".jns_migration_backups/security_20261028_v2_secrets_original.yaml"
def fail(code):
 print("JNS_NATIVE_SECURITY_STAGE_BLOCKED="+code)
 raise SystemExit(71)
if dest.exists() or dest.is_symlink():fail("target_exists")
if not dest.parent.is_dir() or dest.parent.is_symlink():fail("packages_unavailable")
if secrets.is_symlink() or not secrets.is_file():fail("secrets_unavailable")
if backup.exists() or backup.is_symlink():fail("backup_collision")
try:obj=json.loads(base64.b64decode(sys.argv[1],validate=True))
except (ValueError,TypeError):fail("payload_invalid")
src=obj.get("yaml");ref=obj.get("secret_ref");secret=obj.get("secret")
if not isinstance(src,str) or len(src)>210000 or not isinstance(ref,str) or not isinstance(secret,str):fail("payload_bad")
if not re.fullmatch(r"[A-Za-z0-9_.-]{2,90}",ref):fail("secret_name_invalid")
if src.count("initial_state: false")!=6:fail("expected_six_disabled_automations")
if len(re.findall(r"(?m)^\s*-\s*id\s*:",src))!=6:fail("automation_count_invalid")
target_key="jns_security_906_manual_alarm_code_20261028_v2"
if target_key in secrets.read_text():fail("target_secret_key_collision")
try:
 existing=yaml.safe_load(secrets.read_text()) or {}
 if not isinstance(existing,dict):fail("secrets_not_mapping")
except yaml.YAMLError:fail("secrets_unparseable")
backup.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
with backup.open("xb") as f:f.write(secrets.read_bytes());f.flush();os.fsync(f.fileno())
backup.chmod(0o600)
new_value=yaml.safe_dump({target_key:secret},default_flow_style=False,allow_unicode=True)
with secrets.open("ab") as f:
 f.write(("\n# JNS security native manual alarm migration 2026-10-28\n"+new_value).encode())
 f.flush();os.fsync(f.fileno())
src=src.replace("!secret "+ref,"!secret "+target_key)
temp=dest.with_suffix(".yaml.jns-tmp")
if temp.exists():fail("temp_exists")
try:
 with temp.open("xb") as f:f.write(src.encode());f.flush();os.fsync(f.fileno())
 temp.chmod(0o600)
 os.replace(temp,dest)
except BaseException:
 if temp.exists():temp.unlink()
 secrets.write_bytes(backup.read_bytes())
 raise
print("JNS_NATIVE_SECURITY_STAGED="+json.dumps({"manual_alarm_definitions":1,
 "automations_staged_disabled":6,"template_section_present":True,
 "script_section_present":True,"secret_copied_privately":True,
 "core_restarted":False,"original_alarm_vm_unchanged":True},sort_keys=True))
'''
ROLLBACK=r'''
import os,pathlib
root=pathlib.Path("/config")
p=root/"packages/jns_ha_security_native_cutover_20261028_v2.yaml"
s=root/"secrets.yaml"
b=root/".jns_migration_backups/security_20261028_v2_secrets_original.yaml"
if not p.is_file() or p.is_symlink() or not b.is_file() or b.is_symlink():raise SystemExit(70)
p.unlink()
tmp=s.with_name("secrets.yaml.jns-restore-tmp")
if tmp.exists():raise SystemExit(71)
with tmp.open("xb") as f:f.write(b.read_bytes());f.flush();os.fsync(f.fileno())
os.replace(tmp,s)
print("JNS_NATIVE_SECURITY_ROLLBACK=source_secrets_restored_and_package_removed")
'''
def ssh(host,args,timeout=35):
 try:p=subprocess.run(SSH+[host,shlex.join(args)],capture_output=True,text=True,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):return None
 return p.stdout if p.returncode==0 else None
def guest(host,vm,args,timeout=100):
 raw=ssh(host,["qm","guest","exec",str(vm),"--",*args],40)
 if not raw:return None
 try:j=json.loads(raw)
 except ValueError:return None
 deadline=time.monotonic()+timeout
 while time.monotonic()<deadline:
  if j.get("exited"):return j
  if not j.get("pid"):break
  time.sleep(.6)
  raw=ssh(host,["qm","guest","exec-status",str(vm),str(j["pid"])],20)
  if not raw:break
  try:j=json.loads(raw)
  except ValueError:break
 return None
def inside(host,vm,code,args=()):
 c=base64.b64encode(code.encode()).decode()
 return guest(host,vm,["docker","exec","homeassistant","python3","-c",
                       "exec(__import__('base64').b64decode('"+c+"'))",*args])
def marker(j,tag):
 if j and j.get("exitcode")==0:
  lines=[s.split("=",1)[1] for s in str(j.get("out-data","")).splitlines() if s.startswith(tag+"=")]
  if len(lines)==1:return lines[0]
 return None
def main():
 if os.uname().nodename.split(".")[0]!="nodec":
  print("JNS_NATIVE_SECURITY_STAGE_BLOCKED=runner_identity");return 1
 for node,vm in (("nodea",906),("nodeb",905)):
  s=ssh(node,["qm","status",str(vm)])
  if not s or s.strip()!="status: running":
   print("JNS_NATIVE_SECURITY_STAGE_BLOCKED=required_vm_offline");return 1
 b64=base64.b64encode(SOURCE.encode()).decode()
 raw=ssh("nodeb",["python3","-c","exec(__import__('base64').b64decode('"+b64+"'))"],55)
 marks=[s.split("=",1)[1] for s in (raw or "").splitlines() if s.startswith("JNS_PRIVATE_NATIVE_STAGE=")]
 if len(marks)!=1:
  print("JNS_NATIVE_SECURITY_STAGE_BLOCKED=source_structure_unexpected");return 1
 try:
  obj=json.loads(base64.b64decode(marks[0],validate=True))
 except (ValueError,TypeError):
  print("JNS_NATIVE_SECURITY_STAGE_BLOCKED=source_stage_decode");return 1
 j=inside("nodea",906,SECRETS,(obj["secret_ref"],))
 text=marker(j,"JNS_PRIVATE_ALARM_SECRET")
 if not text:
  print("JNS_NATIVE_SECURITY_STAGE_BLOCKED=source_secret_unavailable");return 1
 try:
  secret_obj=json.loads(base64.b64decode(text,validate=True))
  if secret_obj.get("name")!=obj["secret_ref"]:raise ValueError
  obj["secret"]=secret_obj["value"]
 except (TypeError,ValueError,KeyError):
  print("JNS_NATIVE_SECURITY_STAGE_BLOCKED=bad_secret_payload");return 1
 private=base64.b64encode(json.dumps(obj,separators=(",",":")).encode()).decode()
 j=inside("nodeb",905,TARGET,(private,))
 status=marker(j,"JNS_NATIVE_SECURITY_STAGED")
 if not status:
  if j:
   for line in str(j.get("out-data","")).splitlines():
    if line.startswith("JNS_NATIVE_SECURITY_STAGE_BLOCKED="):print(line,flush=True)
  print("JNS_NATIVE_SECURITY_STAGE_BLOCKED=target_write_or_gate_failed");return 1
 print("JNS_NATIVE_SECURITY_STAGED="+status,flush=True)
 chk=guest("nodeb",905,["ha","core","check"],240)
 if not chk or chk.get("exitcode")!=0:
  rb=inside("nodeb",905,ROLLBACK)
  print("JNS_NATIVE_SECURITY_ROLLBACK="+("success" if rb and rb.get("exitcode")==0 else "needs_manual_review"),flush=True)
  print("JNS_NATIVE_SECURITY_STAGE_BLOCKED=ha_core_check_failed");return 1
 print("JNS_NATIVE_SECURITY_HA_CORE_CHECK=passed",flush=True)
 print("JNS_NATIVE_SECURITY_NEEDS_CONTROLLED_RESTART=yes",flush=True)
 return 0
if __name__=="__main__":raise SystemExit(main())
