#!/usr/bin/env python3
"""Read-only porch PIR / security lighting fault isolation on HA-General VM905."""
import subprocess, shlex, base64, json, time
SOURCE=r'''
from pathlib import Path
import yaml,json,re,os,urllib.request
p=Path("/config")
rx=re.compile(r"porch|motion|pir|dog.?s.? run|front.?door|security.?light|welcome.?home|manual.?off",re.I)
def fields(v,depth=0):
 if depth>12:return "...depth-limited..."
 if isinstance(v,list):return [fields(x,depth+1) for x in v[:35]]
 if isinstance(v,dict):
  safe=("alias","id","enabled","initial_state","trigger","triggers","condition","conditions","action","actions","choose","default","sequence","platform","type","domain","device_id","entity_id","to","from","for","event_type","topic","payload","state","above","below","attribute","service","target","data","delay","seconds","minutes","time","after","before","weekday","value_template","template","variables","repeat","count","wait_template","wait_for_trigger","timeout","continue_on_timeout","mode","description")
  return {k:fields(val,depth+1) for k,val in v.items() if k in safe}
 return str(v)[:250]
def reads(name,key):
 try:return json.loads((p/".storage"/name).read_text()).get("data",{}).get(key,[])
 except Exception:return []
entities=reads("core.entity_registry","entities")
device_ids={}
for e in entities:
 if rx.search(" ".join(str(e.get(k,"")) for k in ("entity_id","name","original_name"))):
  device_ids.setdefault(e.get("device_id"),[]).append(e.get("entity_id"))
print("MATCHING_ENTITY_REGISTRY",json.dumps([{"entity":e.get("entity_id"),"name":e.get("name") or e.get("original_name"),"platform":e.get("platform"),"disabled":e.get("disabled_by"),"device":e.get("device_id")} for e in entities if rx.search(" ".join(str(e.get(k,"")) for k in ("entity_id","name","original_name")))][:125])[:16000],flush=True)
for d in reads("core.device_registry","devices"):
 if d.get("id") in device_ids:
  print("DEVICE_OWNER",json.dumps({"name":d.get("name_by_user") or d.get("name"),"model":d.get("model"),"manufacturer":d.get("manufacturer"),"entities":device_ids.get(d.get("id"))},default=str)[:1300],flush=True)
autos=[]
for file in [p/"automations.yaml",*sorted((p/"packages").glob("*.yaml"))]:
 if not file.exists():continue
 try:
  root=yaml.safe_load(file.read_text())
  rows=root if isinstance(root,list) else root.get("automation",[]) if isinstance(root,dict) else []
  if isinstance(rows,dict):
   rows=list(rows.values())
  for a in rows if isinstance(rows,list) else []:
   if isinstance(a,dict):autos.append((str(file.relative_to(p)),a))
 except Exception as e:print("PARSE",file.name,type(e).__name__,flush=True)
print("AUTOMATIONS_TOTAL",len(autos),flush=True)
for path,a in autos:
 if rx.search(json.dumps(fields(a),default=str)):
  print("POSSIBLE_AUTOMATION",json.dumps({"file":path,"configuration":fields(a)},default=str)[:9000],flush=True)
# Read-only view into matching current states through the Supervisor API if Core has access.
token=os.environ.get("SUPERVISOR_TOKEN")
if not token:
 print("LIVE_API","UNAVAILABLE_NO_SUPERVISOR_TOKEN",flush=True)
else:
 try:
  req=urllib.request.Request("http://supervisor/core/api/states",headers={"Authorization":"Bearer "+token})
  with urllib.request.urlopen(req,timeout=6) as res:
   state=json.load(res)
  wanted={e.get("entity_id") for e in entities if rx.search(" ".join(str(e.get(k,"")) for k in ("entity_id","name","original_name")))}
  wanted |= {x.get("entity_id") for x in state if rx.search(str(x.get("entity_id","")))}
  print("LIVE_ENTITY_STATES",json.dumps([{"entity":s.get("entity_id"),"state":s.get("state"),"last_changed":s.get("last_changed"),"last_updated":s.get("last_updated")} for s in state if s.get("entity_id") in wanted][:120])[:13000],flush=True)
 except Exception as e:print("LIVE_API","ERROR",type(e).__name__,flush=True)
print("PORCH_LIGHTING_AUDIT_COMPLETE",flush=True)
'''
def ssh(argv,timeout=30):
 p=subprocess.run(["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","nodeb",shlex.join(argv)],capture_output=True,text=True,timeout=timeout)
 if p.returncode:raise RuntimeError(p.stderr[-300:])
 return json.loads(p.stdout)
code="exec(__import__('base64').b64decode("+repr(base64.b64encode(SOURCE.encode()).decode())+"))"
d=ssh(["qm","guest","exec","905","--","docker","exec","homeassistant","python3","-c",code],30)
for _ in range(28):
 if d.get("exited"):break
 time.sleep(.7)
 d=ssh(["qm","guest","exec-status","905",str(d["pid"])],15)
print("GUEST_EXIT_CODE",d.get("exitcode"),flush=True)
print((d.get("out-data") or "")[:65000],flush=True)
print("GUEST_ERROR",(d.get("err-data") or "")[:600],flush=True)
