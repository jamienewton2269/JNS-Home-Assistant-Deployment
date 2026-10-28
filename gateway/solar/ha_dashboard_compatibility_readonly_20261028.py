#!/usr/bin/env python3
"""Node C -> Node B read-only review of privately staged Lovelace dashboards.

Compares referenced entity IDs against VM905's ENTITY REGISTRY (not live states).
No secrets, dashboard URLs, entity names, or raw config printed. Does not import,
write to HA, change power state, or access a live Home Assistant token.
"""
import base64,json,os,shlex,subprocess

SSH=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=6"]
INNER=r'''
import base64,hashlib,json,os,pathlib,re,subprocess,time,zlib
root=pathlib.Path("/var/lib/jns-solar/consolidation/ha-dashboards-20261028-v1")
if os.geteuid()!=0 or os.uname().nodename.split(".")[0]!="nodeb":raise SystemExit(70)
manifest=root/"manifest.json"
if not manifest.is_file() or manifest.is_symlink():raise SystemExit(71)
m=json.loads(manifest.read_text())
if m.get("target_vm")!=905 or m.get("source_vms")!=[902,906] or not m.get("not_imported"):raise SystemExit(72)
CHECK=r"""import base64,json,pathlib,zlib
p=pathlib.Path("/config/.storage/core.entity_registry")
if p.is_symlink() or not p.is_file():raise SystemExit(70)
entities=json.loads(p.read_text()).get("data",{}).get("entities",[])
ids=[e.get("entity_id") for e in entities if isinstance(e,dict) and isinstance(e.get("entity_id"),str)]
print("JNS_PRIVATE_TARGET_ENTITY_IDS="+base64.b64encode(zlib.compress(json.dumps(ids).encode(),9)).decode())
"""
code=base64.b64encode(CHECK.encode()).decode()
def run(args,timeout=30):
 try:return subprocess.run(args,capture_output=True,text=True,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):return None
p=run(["qm","status","905"])
if not p or p.returncode or p.stdout.strip()!="status: running":raise SystemExit(73)
p=run(["qm","guest","exec","905","--","docker","exec","homeassistant","python3","-c",
       "exec(__import__('base64').b64decode('"+code+"'))"],35)
if not p or p.returncode:raise SystemExit(74)
try:j=json.loads(p.stdout)
except ValueError:raise SystemExit(75)
deadline=time.monotonic()+65
while not j.get("exited") and time.monotonic()<deadline:
 if not j.get("pid"):raise SystemExit(76)
 time.sleep(.5)
 p=run(["qm","guest","exec-status","905",str(j["pid"])],20)
 if not p or p.returncode:raise SystemExit(77)
 try:j=json.loads(p.stdout)
 except ValueError:raise SystemExit(78)
if not j.get("exited") or j.get("exitcode")!=0 or j.get("out-truncated"):raise SystemExit(79)
rows=[v.split("=",1)[1] for v in str(j.get("out-data","")).splitlines()
      if v.startswith("JNS_PRIVATE_TARGET_ENTITY_IDS=")]
if len(rows)!=1:raise SystemExit(80)
target=set(json.loads(zlib.decompress(base64.b64decode(rows[0],validate=True))))
pattern=re.compile(r"\b(?:alarm_control_panel|binary_sensor|button|camera|climate|cover|device_tracker|event|fan|input_boolean|input_number|input_select|input_text|light|lock|media_player|number|person|scene|script|select|sensor|siren|switch|timer|update|weather)\.[a-z][a-z0-9_]*\b")
card=re.compile(r"custom:[a-zA-Z0-9_-]+")
all_refs=set()
totals=[]
for item in m.get("missing_dashboards",[]):
 if not isinstance(item,dict) or item.get("source_vm") not in (902,906):raise SystemExit(81)
 staged=item.get("staged_filename")
 if not isinstance(staged,str) or not re.fullmatch(r"source-(902|906)/[0-9a-f]{20}\.json",staged):raise SystemExit(82)
 f=root/staged
 if f.is_symlink() or not f.is_file():raise SystemExit(83)
 data=f.read_bytes()
 if hashlib.sha256(data).hexdigest()!=item.get("sha256"):raise SystemExit(84)
 cfg=json.loads(data)
 raw=json.dumps(cfg)
 refs=set(pattern.findall(raw))
 all_refs.update(refs)
 missing=refs-target
 domain_counts={}
 for ent in missing:
  domain=ent.split(".",1)[0]
  domain_counts[domain]=domain_counts.get(domain,0)+1
 totals.append({"source_vm":item.get("source_vm"),"registered_entity_references":len(refs&target),
                "references_not_in_vm905_registry":len(missing),
                "missing_reference_domains":dict(sorted(domain_counts.items())),
                "unique_custom_card_types":len(set(card.findall(raw)))})
summary={"staged_dashboard_count":len(totals),"source_dashboard_dependency_counts":totals,
         "distinct_referenced_entities":len(all_refs),
         "entities_present_in_vm905_registry":len(all_refs&target),
         "entities_not_in_vm905_registry":len(all_refs-target),
         "vm905_entity_registry_count":len(target),
         "not_live_state_verification":True,"no_ha_changes":True}
print("JNS_PRIVATE_DASH_DEPENDENCIES="+json.dumps(summary,sort_keys=True))
'''
def main():
 if os.uname().nodename.split(".")[0]!="nodec":
  print("JNS_PRIVATE_DASH_AUDIT_BLOCKED=wrong_runner");return 1
 code=base64.b64encode(INNER.encode()).decode()
 try:
  p=subprocess.run(SSH+["nodeb",shlex.join(["python3","-u","-c",
      "exec(__import__('base64').b64decode('"+code+"'))"])],
      capture_output=True,text=True,timeout=130)
 except (OSError,subprocess.TimeoutExpired):
  print("JNS_PRIVATE_DASH_AUDIT_BLOCKED=nodeb_transport");return 1
 matches=[s for s in p.stdout.splitlines() if s.startswith("JNS_PRIVATE_DASH_DEPENDENCIES=")]
 if p.returncode or len(matches)!=1:
  print("JNS_PRIVATE_DASH_AUDIT_BLOCKED=private_data_or_target_unavailable");return 1
 print(matches[0],flush=True)
 print("JNS_DASHBOARD_COMPATIBILITY_READONLY=yes",flush=True)
 return 0
if __name__=="__main__":raise SystemExit(main())
