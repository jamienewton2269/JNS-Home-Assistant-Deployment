#!/usr/bin/env python3
"""Read-only source VM906 registry-versus-private dashboard reference census.

Probes VM906 via QGA and private staged dashboard on Node B; returns aggregate
counts only. No entity names, credentials, hardware commands, or HA writes.
"""
import base64,collections,json,os,shlex,subprocess,time,zlib
SSH=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=6"]
VM906=r'''
import base64,json,pathlib,sqlite3,zlib
root=pathlib.Path("/config")
reg=root/".storage/core.entity_registry"
if reg.is_symlink() or not reg.is_file():raise SystemExit(70)
entries=json.loads(reg.read_text()).get("data",{}).get("entities",[])
registry={e["entity_id"]:e.get("platform","") for e in entries if isinstance(e,dict)
  and isinstance(e.get("entity_id"),str) and e["entity_id"].startswith("binary_sensor.")}
recorded=[]
database=root/"home-assistant_v2.db"
if database.is_file() and not database.is_symlink():
 try:
  conn=sqlite3.connect("file:"+str(database)+"?mode=ro",uri=True,timeout=2)
  conn.execute("PRAGMA query_only=ON")
  recorded=[e[0] for e in conn.execute(
   "SELECT entity_id FROM states_meta WHERE entity_id LIKE 'binary_sensor.%'")]
  conn.close()
 except (sqlite3.Error,OSError):recorded=[]
# Candidate names from source and target templates; never log identities.
import yaml
from homeassistant.util import slugify
class IgnoreHATags(yaml.SafeLoader):pass
IgnoreHATags.add_multi_constructor("!",lambda loader,suffix,node:None)
candidates=set()
unique_ids=set()
yaml_definitions=0
for f in [root/"configuration.yaml",*sorted((root/"packages").glob("*.yaml"))]:
 if not f.is_file() or f.is_symlink():continue
 try:data=yaml.load(f.read_text(errors="replace"),Loader=IgnoreHATags)
 except (yaml.YAMLError,OSError):continue
 if not isinstance(data,dict):continue
 t=data.get("template",[])
 if isinstance(t,dict):t=[t]
 if not isinstance(t,list):continue
 for group in t:
  if not isinstance(group,dict):continue
  rows=group.get("binary_sensor",[])
  if not isinstance(rows,list):continue
  for row in rows:
   if not isinstance(row,dict):continue
   yaml_definitions+=1
   name=row.get("name")
   if isinstance(name,str) and name:candidates.add("binary_sensor."+slugify(name))
   uid=row.get("unique_id")
   if isinstance(uid,str) and uid:unique_ids.add(uid)
result={"registry":registry,"recorder_ids":recorded,
        "template_slug_candidates":sorted(candidates),
        "template_unique_ids":sorted(unique_ids),
        "template_definitions":yaml_definitions}
print("JNS_PRIVATE_SOURCE_SECURITY_IDS="+base64.b64encode(zlib.compress(json.dumps(result).encode(),9)).decode())
'''
DASHBOARD=r'''
import base64,hashlib,json,os,pathlib,re,zlib
if os.geteuid()!=0 or os.uname().nodename.split(".")[0]!="nodeb":raise SystemExit(70)
root=pathlib.Path("/var/lib/jns-solar/consolidation/ha-dashboards-20261028-v1")
m=json.loads((root/"manifest.json").read_text())
if m.get("target_vm")!=905 or not m.get("not_imported"):raise SystemExit(71)
refs=set()
for item in m["missing_dashboards"]:
 if item.get("source_vm")!=906:continue
 rel=item.get("staged_filename")
 if not isinstance(rel,str) or not re.fullmatch(r"source-906/[a-f0-9]{20}\.json",rel):raise SystemExit(72)
 p=root/rel
 if not p.is_file() or p.is_symlink():raise SystemExit(73)
 raw=p.read_bytes()
 if hashlib.sha256(raw).hexdigest()!=item.get("sha256"):raise SystemExit(74)
 refs.update(re.findall(r"\bbinary_sensor\.[a-z][a-z0-9_]*\b",json.dumps(json.loads(raw))))
print("JNS_PRIVATE_DASHBOARD_SECURITY_IDS="+base64.b64encode(
 zlib.compress(json.dumps(sorted(refs)).encode(),9)).decode())
'''
def run(args,timeout=40):
 try:return subprocess.run(args,capture_output=True,text=True,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):return None
def ssh(node,args,timeout=40):
 return run(SSH+[node,shlex.join(args)],timeout)
def extract(node,args,prefix,timeout=90):
 p=ssh(node,args,timeout)
 if not p or p.returncode:return None
 lines=[x.split("=",1)[1] for x in p.stdout.splitlines() if x.startswith(prefix+"=")]
 if len(lines)!=1:return None
 try:return json.loads(zlib.decompress(base64.b64decode(lines[0],validate=True)))
 except (ValueError,zlib.error,TypeError):return None
def guest(node,vm):
 code=base64.b64encode(VM906.encode()).decode()
 p=ssh(node,["qm","guest","exec",str(vm),"--","docker","exec",
 "homeassistant","python3","-c","exec(__import__('base64').b64decode('"+code+"'))"],40)
 if not p or p.returncode:return None
 try:j=json.loads(p.stdout)
 except ValueError:return None
 until=time.monotonic()+65
 while not j.get("exited") and time.monotonic()<until:
  if not j.get("pid"):return None
  time.sleep(.5)
  p=ssh(node,["qm","guest","exec-status",str(vm),str(j["pid"])],24)
  if not p or p.returncode:return None
  try:j=json.loads(p.stdout)
  except ValueError:return None
 if not j.get("exited") or j.get("exitcode")!=0 or j.get("out-truncated"):return None
 lines=[x.split("=",1)[1] for x in str(j.get("out-data","")).splitlines() if x.startswith("JNS_PRIVATE_SOURCE_SECURITY_IDS=")]
 if len(lines)!=1:return None
 try:return json.loads(zlib.decompress(base64.b64decode(lines[0],validate=True)))
 except (ValueError,zlib.error,TypeError):return None
def main():
 if os.uname().nodename.split(".")[0]!="nodec":
  print("JNS_SECURITY_SOURCE_AUDIT_BLOCKED=runner_identity");return 1
 state=ssh("nodea",["qm","status","906"],20)
 if not state or state.returncode or state.stdout.strip()!="status: running":
  print("JNS_SECURITY_SOURCE_AUDIT_BLOCKED=source_offline");return 1
 sec=guest("nodea",906)
 target=guest("nodeb",905)
 code=base64.b64encode(DASHBOARD.encode()).decode()
 dash=extract("nodeb",["python3","-u","-c",
  "exec(__import__('base64').b64decode('"+code+"'))"],
  "JNS_PRIVATE_DASHBOARD_SECURITY_IDS",40)
 if sec is None or target is None or dash is None:
  print("JNS_SECURITY_SOURCE_AUDIT_BLOCKED=private_data_unavailable");return 1
 names=set(dash)
 registry=sec["registry"]
 recorded=set(sec["recorder_ids"])
 present=names&set(registry)
 platforms=collections.Counter(str(registry[s]) for s in present)
 print("JNS_SECURITY_SOURCE_DASHBOARD_REFERENCES="+json.dumps({
  "source_dashboard_binary_references":len(names),
  "references_registered_on_vm906":len(present),
  "references_seen_in_vm906_recorder_metadata":len(names&recorded),
  "references_not_in_vm906_registry":len(names-set(registry)),
  "source_vm906_binary_registry_total":len(registry),
  "matched_reference_platforms":dict(sorted(platforms.items())),
  "vm906_yaml_binary_definitions":sec["template_definitions"],
  "vm905_yaml_binary_definitions":target["template_definitions"],
  "vm906_name_slug_candidates":len(sec["template_slug_candidates"]),
  "vm905_name_slug_candidates":len(target["template_slug_candidates"]),
  "source_target_template_slug_overlap":len(set(sec["template_slug_candidates"])&set(target["template_slug_candidates"])),
  "source_target_template_unique_id_overlap":len(set(sec["template_unique_ids"])&set(target["template_unique_ids"])),
  "dashboard_refs_matching_vm906_template_name_slugs":len(names&set(sec["template_slug_candidates"])),
  "dashboard_refs_matching_vm905_template_name_slugs":len(names&set(target["template_slug_candidates"])),
  "state_metadata_not_live_control_proof":True,
  "no_source_or_target_changes":True},sort_keys=True),flush=True)
 return 0
if __name__=="__main__":raise SystemExit(main())
