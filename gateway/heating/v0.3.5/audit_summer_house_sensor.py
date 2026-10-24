#!/usr/bin/env python3
"""Read-only Summer House TS0201 -> HA-General heating source mapping audit.

No secrets, service calls, configuration or device changes. Runs only in the
existing JNS Node C -> Node B -> VM905 QGA trust path.
"""
import base64,json,sys,time
sys.path.insert(0,"gateway/arrival_lighting")
from readiness_probe import ssh_host

GUEST = r'''
import ast,datetime,hashlib,json,pathlib,re,sqlite3
root=pathlib.Path("/config")
ieee="0xa4c13880bb5cffff"
storage=root/".storage"
out={"ieee":ieee,"candidates":[],"heating_config":[],"heating_code":{},"recorder":{}}
def doc(name):
 return json.loads((storage/name).read_text())["data"]
devices=doc("core.device_registry")["devices"]
entities=doc("core.entity_registry")["entities"]
dev_ids=set()
for d in devices:
 blobs=[str(d.get(k) or "") for k in ("name","name_by_user","manufacturer","model")]
 blobs += [str(x) for x in d.get("identifiers",[]) + d.get("connections",[])]
 selected=(ieee.lower() in " ".join(blobs).lower()
    or ("summer house sensor" in " ".join(blobs).lower() and
        re.search("ts0201|tuya|temperature|zigbee", " ".join(blobs), re.I)))
 if selected:
  dev_ids.add(d.get("id"))
  out["candidates"].append({"kind":"device","name":d.get("name_by_user") or d.get("name"),
      "manufacturer":d.get("manufacturer"),"model":d.get("model"),"matching_ieee":ieee.lower() in " ".join(blobs).lower(),
      "device_id_suffix":str(d.get("id"))[-6:]})
matching=[]
for e in entities:
 blob=" ".join(str(e.get(k) or "") for k in ("entity_id","original_name","name"))
 if e.get("device_id") in dev_ids or "summer_house_sensor" in blob.lower().replace(" ","_"):
  if e.get("entity_id","").startswith(("sensor.","binary_sensor.")):
   matching.append({"kind":"entity","entity_id":e.get("entity_id"),
       "platform":e.get("platform"),"original_name":e.get("original_name"),
       "disabled_by":e.get("disabled_by"),
       "matched_device":e.get("device_id") in dev_ids})
out["candidates"].extend(matching[:40])
entries=doc("core.config_entries")["entries"]
for e in entries:
 if e.get("domain")!="jns_heating_zones":continue
 config={"entry_id_suffix":str(e.get("entry_id"))[-7:],
          "disabled_by":e.get("disabled_by")}
 for key in ("data","options"):
  fields=e.get(key) or {}
  config[key+"_keys"]=sorted(fields.keys())
  refs={}
  for k,v in fields.items():
   if isinstance(v,str) and re.fullmatch(r"(sensor|weather|climate|binary_sensor|input_number)\.[a-zA-Z0-9_]+",v):
    refs[k]=v
  config[key+"_entity_refs"]=refs
 out["heating_config"].append(config)
# Inspect MQTT registry configuration, options handlers and coordinator
# source-selection semantics without exporting credentials.
out["config_approval"]={}
try:
 import ast
 code=(root/"custom_components/jns_heating_zones/config_flow.py").read_text()
 tree=ast.parse(code)
 out["config_approval"]["flow_handlers"]=[n.name for n in ast.walk(tree)
    if isinstance(n,(ast.AsyncFunctionDef,ast.FunctionDef)) and
    ("option" in n.name or "step" in n.name)]
except Exception as err:out["config_approval"]["error"]=type(err).__name__
comp=root/"custom_components/jns_heating_zones"
for p in sorted(comp.glob("*.py")):
 if p.name not in ("coordinator.py","config_flow.py","const.py","__init__.py"):continue
 code=p.read_text()
 lines=code.splitlines()
 pairs=[]
 for i,line in enumerate(lines,1):
  if re.search(r"(?i)(outdoor|weather_entity|external_temp|indoor_temp|options\\.get|entry\\.data|CONF_.*TEMP)",line):
   if not re.search(r"(?i)(token|auth|key|client|secret|password)",line):
    pairs.append(f"{i}:{line[:165]}")
 out["heating_code"][p.name]={"sha256":hashlib.sha256(p.read_bytes()).hexdigest(),"selected_lines":pairs[:70]}
db=root/"home-assistant_v2.db"
if db.exists():
 try:
  con=sqlite3.connect("file:"+str(db)+"?mode=ro",uri=True,timeout=4)
  ids={x["entity_id"] for x in matching}
  ids.update(["sensor.thermostat_thermostat_outdoor_temperature",
      "sensor.thermostat_thermostat_indoor_temperature"])
  now=datetime.datetime.now(datetime.timezone.utc).timestamp()
  for entity in sorted(ids):
   if not entity.startswith("sensor."):continue
   rows=con.execute("""SELECT s.state,s.last_updated_ts FROM states s
    JOIN states_meta m ON s.metadata_id=m.metadata_id
    WHERE m.entity_id=? ORDER BY s.last_updated_ts DESC LIMIT 3""",(entity,)).fetchall()
   out["recorder"][entity]=[{"value":s,"age_minutes":round((now-t)/60,1)}
      for s,t in rows if t is not None]
  con.close()
 except Exception as err:out["recorder_error"]=type(err).__name__
# Capture safe coordinator source snippets: no secrets or stored samples.
for filename in ("coordinator.py","__init__.py","config_flow.py"):
 p=comp/filename
 if p.is_file():
  lines=p.read_text().splitlines()
  if filename=="coordinator.py":
   selected=[f"{i+1}:{line[:160]}" for i,line in enumerate(lines[:95])
       if not re.search(r"(?i)(token|password|secret|api_key|authorization)",line)]
  elif filename=="__init__.py":
   selected=[f"{i+1}:{line[:160]}" for i,line in enumerate(lines[:85])
       if not re.search(r"(?i)(token|password|secret|api_key|authorization)",line)]
  else:
   selected=[f"{i+1}:{line[:160]}" for i,line in enumerate(lines[:85])
       if not re.search(r"(?i)(token|password|secret|api_key|authorization)",line)]
  out.setdefault("safe_implementation_excerpt",{})[filename]=selected
print(json.dumps(out,sort_keys=True))
'''
expr="exec(__import__('base64').b64decode('"+base64.b64encode(GUEST.encode()).decode()+"'))"
r=json.loads(ssh_host("nodeb",["qm","guest","exec","905","--","docker","exec","homeassistant","python3","-c",expr]))
deadline=time.monotonic()+110
while not r.get("exited"):
 if not isinstance(r.get("pid"),int) or time.monotonic()>deadline:
  raise RuntimeError("VM905 device audit timed out")
 time.sleep(1)
 r=json.loads(ssh_host("nodeb",["qm","guest","exec-status","905",str(r["pid"])]))
if r.get("exitcode")!=0:
 print("JNS_HEATING_TS0201_AUDIT_ERROR",str(r.get("err-data",""))[-650:])
 raise SystemExit(2)
data=json.loads(r.get("out-data") or "{}")
print("JNS_HEATING_TS0201_AUDIT",json.dumps(data,sort_keys=True))
