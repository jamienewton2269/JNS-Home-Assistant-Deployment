#!/usr/bin/env python3
"""Private Node B cross-check of HA-Security dashboard versus HA-General templates.

Read-only: never modifies HA config/registries/states, never restarts or
controls devices. No entity IDs, secrets, dashboard URLs, or raw YAML in CI logs.
"""
import base64, json, os, shlex, subprocess

SSH=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=6"]
GUEST=r'''
import base64,json,pathlib,re,sqlite3,zlib
import yaml
from homeassistant.util import slugify
root=pathlib.Path("/config")
p=root/"packages/jns_ha_security_native_cutover_20261028_v2.yaml"
if not p.is_file() or p.is_symlink():raise SystemExit(70)
class NoSecretLoader(yaml.SafeLoader):pass
NoSecretLoader.add_multi_constructor("!",lambda loader,suffix,node:None)
data=yaml.load(p.read_text(),Loader=NoSecretLoader)
if not isinstance(data,dict):raise SystemExit(71)
templ=data.get("template",[])
if not isinstance(templ,list):raise SystemExit(72)
names=[]
for group in templ:
 if not isinstance(group,dict):continue
 for item in group.get("binary_sensor",[]):
  if isinstance(item,dict):
   label=item.get("name")
   if isinstance(label,str) and label:
    names.append("binary_sensor."+slugify(label))
registry=root/".storage/core.entity_registry"
ids=set()
if registry.is_file() and not registry.is_symlink():
 for item in json.loads(registry.read_text()).get("data",{}).get("entities",[]):
  if isinstance(item,dict) and isinstance(item.get("entity_id"),str):
   ids.add(item["entity_id"])
recorded=set()
database=root/"home-assistant_v2.db"
if database.is_file() and not database.is_symlink():
 try:
  db=sqlite3.connect("file:"+str(database)+"?mode=ro",uri=True,timeout=2)
  db.execute("PRAGMA query_only=ON")
  recorded={row[0] for row in db.execute(
    "SELECT entity_id FROM states_meta WHERE entity_id LIKE 'binary_sensor.%' OR entity_id LIKE 'input_number.%' OR entity_id LIKE 'alarm_control_panel.%'")}
  db.close()
 except (sqlite3.Error,OSError):
  recorded=set()
payload={"yaml_template_candidates":sorted(set(names)),
         "template_definition_total":sum(len(g.get("binary_sensor",[])) for g in templ if isinstance(g,dict) and isinstance(g.get("binary_sensor",[]),list)),
         "registry_ids":sorted(ids),"recorder_meta_ids":sorted(recorded),
         "package_alarm_section":bool(data.get("alarm_control_panel")),
         "package_input_number_section":bool(data.get("input_number"))}
print("JNS_PRIVATE_TEMPLATE_COVERAGE="+base64.b64encode(
 zlib.compress(json.dumps(payload,separators=(",",":")).encode(),9)).decode())
'''
HOST=r'''
import base64,hashlib,json,os,pathlib,re,subprocess,time,zlib
if os.geteuid()!=0 or os.uname().nodename.split(".")[0]!="nodeb":raise SystemExit(70)
root=pathlib.Path("/var/lib/jns-solar/consolidation/ha-dashboards-20261028-v1")
manifest=root/"manifest.json"
if manifest.is_symlink() or not manifest.is_file():raise SystemExit(71)
m=json.loads(manifest.read_text())
if m.get("target_vm")!=905 or not m.get("not_imported"):raise SystemExit(72)
pattern=re.compile(r"\b(?:binary_sensor|input_number|alarm_control_panel)\.[a-z][a-z0-9_]*\b")
wanted=set()
for item in m.get("missing_dashboards",[]):
 if item.get("source_vm")!=906:continue
 rel=item.get("staged_filename")
 if not isinstance(rel,str) or not re.fullmatch(r"source-906/[a-f0-9]{20}\.json",rel):raise SystemExit(73)
 p=root/rel
 if p.is_symlink() or not p.is_file():raise SystemExit(74)
 raw=p.read_bytes()
 if hashlib.sha256(raw).hexdigest()!=item.get("sha256"):raise SystemExit(75)
 wanted.update(pattern.findall(json.dumps(json.loads(raw))))
cmd=["qm","status","905"]
def run(args,timeout=25):
 try:return subprocess.run(args,capture_output=True,text=True,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):return None
q=run(cmd)
if not q or q.returncode or q.stdout.strip()!="status: running":raise SystemExit(76)
code="INNER_BASE64"
q=run(["qm","guest","exec","905","--","docker","exec","homeassistant","python3","-c",
       "exec(__import__('base64').b64decode('"+code+"'))"],45)
if not q or q.returncode:raise SystemExit(77)
try:j=json.loads(q.stdout)
except ValueError:raise SystemExit(78)
deadline=time.monotonic()+60
while not j.get("exited") and time.monotonic()<deadline:
 if not j.get("pid"):raise SystemExit(79)
 time.sleep(.5)
 q=run(["qm","guest","exec-status","905",str(j["pid"])],18)
 if not q or q.returncode:raise SystemExit(80)
 try:j=json.loads(q.stdout)
 except ValueError:raise SystemExit(81)
if not j.get("exited") or j.get("exitcode")!=0 or j.get("out-truncated"):raise SystemExit(82)
vals=[x.split("=",1)[1] for x in str(j.get("out-data","")).splitlines()
      if x.startswith("JNS_PRIVATE_TEMPLATE_COVERAGE=")]
if len(vals)!=1:raise SystemExit(83)
try:
 body=zlib.decompress(base64.b64decode(vals[0],validate=True))
 if len(body)>2000000:raise ValueError("oversize")
 result=json.loads(body)
except (ValueError,zlib.error):raise SystemExit(84)
templates=set(result["yaml_template_candidates"])
registry=set(result["registry_ids"])
recorder=set(result["recorder_meta_ids"])
binary={x for x in wanted if x.startswith("binary_sensor.")}
inp={x for x in wanted if x.startswith("input_number.")}
summary={
 "source_dashboard_binary_references":len(binary),
 "v2_template_binary_definitions":result["template_definition_total"],
 "v2_template_candidate_ids":len(templates),
 "dashboard_binary_matching_template_name_slugs":len(binary&templates),
 "dashboard_binary_present_in_entity_registry":len(binary&registry),
 "dashboard_binary_seen_in_recorder_metadata":len(binary&recorder),
 "dashboard_binary_not_matching_template_name_slugs":len(binary-templates),
 "dashboard_input_number_references":len(inp),
 "dashboard_input_number_registered":len(inp&registry),
 "dashboard_input_number_seen_in_recorder":len(inp&recorder),
 "v2_manual_alarm_definition_present":result["package_alarm_section"],
 "v2_input_number_section_present":result["package_input_number_section"],
 "recorder_metadata_not_live_state_proof":True,
 "no_ha_config_or_device_changes":True}
print("JNS_SECURITY_TEMPLATE_COVERAGE="+json.dumps(summary,sort_keys=True))
'''
def main():
 if os.uname().nodename.split(".")[0]!="nodec":
  print("JNS_SECURITY_TEMPLATE_AUDIT_BLOCKED=runner_identity");return 1
 host=HOST.replace("INNER_BASE64",base64.b64encode(GUEST.encode()).decode())
 script=base64.b64encode(host.encode()).decode()
 try:
  p=subprocess.run(SSH+["nodeb",shlex.join(["python3","-u","-c",
   "exec(__import__('base64').b64decode('"+script+"'))"])],
   capture_output=True,text=True,timeout=125)
 except (OSError,subprocess.TimeoutExpired):
  print("JNS_SECURITY_TEMPLATE_AUDIT_BLOCKED=transport");return 1
 filtered=[x for x in p.stdout.splitlines() if x.startswith("JNS_SECURITY_TEMPLATE_COVERAGE=")]
 if p.returncode or len(filtered)!=1:
  print("JNS_SECURITY_TEMPLATE_AUDIT_BLOCKED=source_or_guest_probe");return 1
 print(filtered[0],flush=True)
 print("JNS_SECURITY_TEMPLATE_AUDIT_READ_ONLY=yes",flush=True)
 return 0
if __name__=="__main__":raise SystemExit(main())
