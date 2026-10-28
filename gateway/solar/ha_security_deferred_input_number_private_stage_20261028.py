#!/usr/bin/env python3
"""Inertly stage VM906's remaining input_number helper in Node B private storage.

No /config writes, Home Assistant registry edits, Core restarts, device commands,
or source shutdowns. Refuse every observed target YAML/UI/registry collision.
Never print private helper definition, entity ID, or stage file contents.
"""
import base64,json,os,shlex,subprocess,time,zlib
SSH=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=6"]
GUEST=r'''
import base64,json,pathlib,yaml,zlib
root=pathlib.Path("/config")
class IgnoreHATags(yaml.SafeLoader):pass
IgnoreHATags.add_multi_constructor("!",lambda loader,suffix,node:None)
numbers={}
for f in [root/"configuration.yaml",*sorted((root/"packages").glob("*.yaml"))]:
 if not f.is_file() or f.is_symlink():continue
 try:obj=yaml.load(f.read_text(errors="replace"),Loader=IgnoreHATags)
 except (yaml.YAMLError,OSError):continue
 if isinstance(obj,dict) and isinstance(obj.get("input_number"),dict):
  for k,v in obj["input_number"].items():
   if isinstance(k,str):numbers[k]=v
entities=root/".storage/core.entity_registry"
reg=set()
if entities.is_file() and not entities.is_symlink():
 for item in json.loads(entities.read_text()).get("data",{}).get("entities",[]):
  if isinstance(item,dict) and isinstance(item.get("entity_id"),str) and item["entity_id"].startswith("input_number."):
   reg.add(item["entity_id"])
store=root/".storage/input_number"
ui=set()
if store.is_file() and not store.is_symlink():
 o=json.loads(store.read_text()).get("data",{})
 for i in o.get("items",[]) if isinstance(o,dict) else []:
  if isinstance(i,dict) and isinstance(i.get("id"),str):ui.add(i["id"])
payload={"yaml":numbers,"registered":sorted(reg),"ui_ids":sorted(ui)}
print("JNS_PRIVATE_HELPER_INPUT="+base64.b64encode(zlib.compress(
 json.dumps(payload,sort_keys=True).encode(),9)).decode())
'''
WRITE=r'''
import hashlib,json,os,pathlib,sys,tempfile,yaml
if os.geteuid()!=0 or os.uname().nodename.split(".")[0]!="nodeb":raise SystemExit(71)
root=pathlib.Path("/var/lib/jns-solar/consolidation/ha-security-906-20261027-v1")
manifest=root/"manifest.json"
target=root/"deferred-input-number-20261028-v1.yaml"
if not root.is_dir() or root.is_symlink() or not manifest.is_file() or manifest.is_symlink():raise SystemExit(72)
if target.exists() or target.is_symlink():raise SystemExit(73)
m=json.loads(manifest.read_text())
if m.get("source_vm")!=906 or m.get("target_vm")!=905:raise SystemExit(74)
obj=json.loads(sys.stdin.read(20000))
if obj.get("source_vm")!=906 or obj.get("target_vm")!=905:raise SystemExit(75)
data=obj.get("input_number")
if not isinstance(data,dict) or len(data)!=1:raise SystemExit(76)
key=next(iter(data))
if not isinstance(key,str) or not key or len(key)>128:raise SystemExit(77)
body=yaml.safe_dump({"input_number":data},sort_keys=False,allow_unicode=True)
p=pathlib.Path(tempfile.mkstemp(prefix=".jns-security-helper-",dir=root)[1])
try:
 p.chmod(0o600)
 p.write_text("# INERT PRIVATE STAGE - do not include into production before guarded cutover\n"+body)
 with p.open("rb") as f:os.fsync(f.fileno())
 if target.exists():raise SystemExit(78)
 p.rename(target)
except BaseException:
 p.unlink(missing_ok=True)
 raise
print("JNS_DEFERRED_HELPER_PRIVATE_STAGE="+json.dumps({
 "source_vm":906,"target_vm":905,"definition_count":1,"stored_privately":True,
 "yaml_sha256_verified":bool(hashlib.sha256(target.read_bytes()).hexdigest()),
 "target_HA_config_modified":False,"controller_changed":False},sort_keys=True))
'''
def ssh(host,args,stdin=None,timeout=40):
 try:return subprocess.run(SSH+[host,shlex.join(args)],input=stdin,
                           capture_output=True,text=True,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):return None
def guest(host,vm):
 code=base64.b64encode(GUEST.encode()).decode()
 r=ssh(host,["qm","guest","exec",str(vm),"--","docker","exec","homeassistant",
  "python3","-c","exec(__import__('base64').b64decode('"+code+"'))"],timeout=45)
 if not r or r.returncode:return None
 try:j=json.loads(r.stdout)
 except ValueError:return None
 until=time.monotonic()+70
 while not j.get("exited") and time.monotonic()<until:
  if not j.get("pid"):return None
  time.sleep(.5)
  r=ssh(host,["qm","guest","exec-status",str(vm),str(j["pid"])],timeout=24)
  if not r or r.returncode:return None
  try:j=json.loads(r.stdout)
  except ValueError:return None
 if not j.get("exited") or j.get("exitcode")!=0 or j.get("out-truncated"):return None
 out=[x.split("=",1)[1] for x in str(j.get("out-data","")).splitlines()
      if x.startswith("JNS_PRIVATE_HELPER_INPUT=")]
 if len(out)!=1:return None
 try:return json.loads(zlib.decompress(base64.b64decode(out[0],validate=True)))
 except (ValueError,zlib.error,TypeError):return None
def no_null(v):
 if v is None:return False
 if isinstance(v,dict):return all(no_null(k) and no_null(x) for k,x in v.items())
 if isinstance(v,list):return all(no_null(x) for x in v)
 return isinstance(v,(str,int,float,bool))
def main():
 if os.uname().nodename.split(".")[0]!="nodec":
  print("JNS_DEFERRED_HELPER_STAGE_BLOCKED=runner_identity");return 1
 for host,vm in (("nodea",906),("nodeb",905)):
  p=ssh(host,["qm","status",str(vm)],timeout=20)
  if not p or p.returncode or p.stdout.strip()!="status: running":
   print("JNS_DEFERRED_HELPER_STAGE_BLOCKED=source_target_state");return 1
 src=guest("nodea",906)
 dst=guest("nodeb",905)
 if src is None or dst is None:
  print("JNS_DEFERRED_HELPER_STAGE_BLOCKED=private_probe_failed");return 1
 fields=src.get("yaml",{})
 if not isinstance(fields,dict) or len(fields)!=1:
  print("JNS_DEFERRED_HELPER_STAGE_BLOCKED=not_exactly_one_source_helper");return 1
 name=next(iter(fields))
 if not no_null(fields[name]):
  print("JNS_DEFERRED_HELPER_STAGE_BLOCKED=source_helper_contains_unsupported_value");return 1
 if name in dst.get("yaml",{}) or name in dst.get("ui_ids",[]) or ("input_number."+name) in dst.get("registered",[]):
  print("JNS_DEFERRED_HELPER_STAGE_BLOCKED=target_collision");return 1
 payload=json.dumps({"source_vm":906,"target_vm":905,"input_number":fields})
 code=base64.b64encode(WRITE.encode()).decode()
 r=ssh("nodeb",["python3","-u","-c",
  "exec(__import__('base64').b64decode('"+code+"'))"],
  stdin=payload,timeout=45)
 if not r or r.returncode:
  print("JNS_DEFERRED_HELPER_STAGE_BLOCKED=private_destination");return 1
 safe=[x for x in r.stdout.splitlines() if x.startswith("JNS_DEFERRED_HELPER_PRIVATE_STAGE=")]
 if len(safe)!=1:
  print("JNS_DEFERRED_HELPER_STAGE_BLOCKED=no_attestation");return 1
 print(safe[0],flush=True)
 print("JNS_SECURITY_INPUT_HELPER_INERT_ONLY=yes",flush=True)
 return 0
if __name__=="__main__":raise SystemExit(main())
