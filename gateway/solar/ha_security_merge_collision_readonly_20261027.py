#!/usr/bin/env python3
"""Read-only collision and manual-alarm dependency assessment of staged VM906
security YAML vs live VM905 YAML. No raw names, ids, paths, secrets or config
content emitted to public CI. No guest or host changes.
"""
import base64,hashlib,hmac,json,os,re,secrets,shlex,subprocess,sys,time
SSH=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=6"]
COLLECT=r'''
import base64,hashlib,hmac,json,pathlib,re,sys
salt=bytes.fromhex(sys.argv[1])
root=pathlib.Path("/config")
def sig(s):
 return hmac.new(salt,s.encode(),hashlib.sha256).hexdigest()
def readfile(p):
 try:
  if p.is_symlink() or not p.is_file() or p.stat().st_size>1024*1024:return ""
  return p.read_text(errors="replace")
 except (OSError,PermissionError):return ""
files=[root/n for n in ("configuration.yaml","automations.yaml","scripts.yaml","scenes.yaml")]
p=root/"packages"
if p.is_dir() and not p.is_symlink():
 files.extend(sorted(p.rglob("*.yaml"))[:70])
payload=[]
for f in files:
 t=readfile(f)
 if not t:continue
 payload.append((f.name,t))
print("JNS_PRIVATE_TARGET="+base64.b64encode(json.dumps(payload,separators=(",",":")).encode()).decode())
'''
AUDIT=r'''
import base64,hashlib,hmac,json,os,pathlib,re,sys
salt=bytes.fromhex(sys.argv[1])
stage=pathlib.Path("/var/lib/jns-solar/consolidation/ha-security-906-20261027-v1")
manifest=stage/"manifest.json"
def fail(c):
 print("JNS_SECURITY_COLLISION_BLOCKED="+c,flush=True);raise SystemExit(77)
if os.geteuid()!=0 or os.uname().nodename.split(".")[0]!="nodeb":fail("wrong_host")
if not manifest.is_file() or manifest.is_symlink():fail("stage_manifest_missing")
try:meta=json.loads(manifest.read_text())
except (OSError,ValueError):fail("bad_manifest")
if meta.get("source_vm")!=906 or meta.get("target_vm")!=905 or not meta.get("stage_inert"):fail("stage_identity")
try:target=json.loads(sys.stdin.buffer.read(4500000))
except (OSError,ValueError):fail("invalid_target_private_payload")
if not isinstance(target,list) or not 10<=len(target)<=90:fail("target_file_inventory_invalid")
def sig(s):
 return hmac.new(salt,s.encode(),hashlib.sha256).hexdigest()
def analyze(items):
 types=("input_boolean","input_number","input_select","input_text","timer",
        "counter","group","script")
 out={"defined":{},"automation_ids":set(),"script_keys":set(),
      "package_names":set(),"main_alarm_present":False,"main_alarm_manual":False,
      "yaml_items":0}
 for name,body,category in items:
  if not isinstance(body,str):continue
  out["yaml_items"]+=1
  if name=="configuration.yaml":
   match=re.search(r"(?ms)^alarm_control_panel\s*:\s*(.*?)(?=^[A-Za-z][\w]*\s*:|\Z)",body)
   if match:
    out["main_alarm_present"]=True
    out["main_alarm_manual"]=bool(re.search(r"(?m)^\s*-?\s*platform\s*:\s*manual\b",match.group(1)))
  if category=="package":out["package_names"].add(sig(name))
  lines=body.splitlines()
  parent=None
  for line in lines:
   m=re.match(r"^([a-z][a-z0-9_]*)\s*:",line)
   if m:parent=m.group(1);continue
   if parent in types:
    key=re.match(r"^  ([a-zA-Z][a-zA-Z0-9_]*)\s*:",line)
    if key:
     out["defined"].setdefault(parent,set()).add(sig(parent+"."+key.group(1)))
   m=re.match(r"^\s*-\s*id\s*:\s*['\"]?([a-zA-Z0-9_-]{2,90})",line)
   if m:out["automation_ids"].add(sig(m.group(1)))
 return out
source=[]
for row in meta.get("files",[]):
 p=stage/"files"/str(row.get("staged_basename",""))
 if not p.is_file() or p.is_symlink():fail("source_stage_file_missing")
 data=p.read_bytes()
 if hashlib.sha256(data).hexdigest()!=row.get("sha256"):fail("source_stage_checksum_mismatch")
 source.append((row.get("original_basename",""),data.decode("utf-8","replace"),row.get("kind","")))
if len(source)!=6:fail("unexpected_source_file_count")
a=analyze(source)
b=analyze([(x[0],x[1],"package" if x[0] not in ("configuration.yaml","automations.yaml","scripts.yaml","scenes.yaml") else "root")
           for x in target if isinstance(x,list) and len(x)==2])
collision={name:len(a["defined"].get(name,set())&b["defined"].get(name,set()))
           for name in set(a["defined"])|set(b["defined"])}
summ={"source_yaml_files":a["yaml_items"],"target_yaml_files":b["yaml_items"],
      "source_main_alarm_present":a["main_alarm_present"],
      "source_main_manual_alarm":a["main_alarm_manual"],
      "target_main_alarm_present":b["main_alarm_present"],
      "source_package_count":len(a["package_names"]),
      "target_package_count":len(b["package_names"]),
      "package_basename_collisions":len(a["package_names"]&b["package_names"]),
      "source_helper_definitions_by_type":{k:len(v) for k,v in a["defined"].items()},
      "helper_definition_name_collisions_by_type":{k:v for k,v in collision.items() if v},
      "automation_yaml_id_collisions":len(a["automation_ids"]&b["automation_ids"]),
      "source_automation_id_count":len(a["automation_ids"]),
      "target_automation_id_count":len(b["automation_ids"]),
      "safe_to_bulk_copy":False,
      "assessment":"requires_selection_and_esp_home_reenrolment"}
print("JNS_SECURITY_MERGE_COLLISION_REPORT="+json.dumps(summ,sort_keys=True),flush=True)
'''
def ssh(node,args,stdin=None,timeout=35):
 try:return subprocess.run(SSH+[node,shlex.join(args)],input=stdin,
                          text=True,capture_output=True,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):return None
def main():
 if os.uname().nodename.split(".")[0]!="nodec":
  print("JNS_SECURITY_COLLISION_BLOCKED=wrong_runner",flush=True);return 1
 salt=secrets.token_hex(24)
 code=base64.b64encode(COLLECT.encode()).decode()
 q=ssh("nodeb",["qm","guest","exec","905","--","docker","exec","homeassistant",
                "python3","-c","exec(__import__('base64').b64decode('"+code+"'))",salt],timeout=45)
 if not q or q.returncode:
  print("JNS_SECURITY_COLLISION_BLOCKED=target_guest_agent_unavailable",flush=True);return 1
 try:j=json.loads(q.stdout)
 except ValueError:
  print("JNS_SECURITY_COLLISION_BLOCKED=target_agent_reply",flush=True);return 1
 for _ in range(45):
  if j.get("exited"):break
  if not j.get("pid"):break
  time.sleep(.3)
  r=ssh("nodeb",["qm","guest","exec-status","905",str(j["pid"])],timeout=18)
  if not r or r.returncode:break
  try:j=json.loads(r.stdout)
  except ValueError:break
 if not j.get("exited") or j.get("exitcode")!=0 or j.get("out-truncated"):
  print("JNS_SECURITY_COLLISION_BLOCKED=target_exec_failed",flush=True);return 1
 found=[x.split("=",1)[1] for x in (j.get("out-data") or "").splitlines() if x.startswith("JNS_PRIVATE_TARGET=")]
 if len(found)!=1:
  print("JNS_SECURITY_COLLISION_BLOCKED=target_missing",flush=True);return 1
 try:payload=base64.b64decode(found[0],validate=True).decode()
 except (ValueError,UnicodeDecodeError):
  print("JNS_SECURITY_COLLISION_BLOCKED=target_decode",flush=True);return 1
 runner=base64.b64encode(AUDIT.encode()).decode()
 result=ssh("nodeb",["python3","-u","-c","exec(__import__('base64').b64decode('"+runner+"'))",salt],
            stdin=payload,timeout=90)
 if not result or result.returncode:
  for row in (result.stdout if result else "").splitlines():
   if row.startswith("JNS_SECURITY_COLLISION_BLOCKED="):print(row,flush=True)
  print("JNS_SECURITY_COLLISION_BLOCKED=analysis_failed",flush=True);return 1
 rows=[row for row in result.stdout.splitlines() if row.startswith("JNS_SECURITY_MERGE_COLLISION_REPORT=")]
 if len(rows)!=1:
  print("JNS_SECURITY_COLLISION_BLOCKED=missing_report",flush=True);return 1
 print(rows[0],flush=True)
 print("JNS_NO_PRODUCTION_CHANGE=yes",flush=True)
 return 0
if __name__=="__main__":sys.exit(main())
