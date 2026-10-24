#!/usr/bin/env python3
"""Read-only matching of porch PIR trigger and labeled security-light targets."""
import subprocess,shlex,json,base64,time
SOURCE=r'''
from pathlib import Path
import yaml,json,re,sqlite3,os
P=Path("/config")
def registry(name,key):
 try:return json.loads((P/".storage"/name).read_text()).get("data",{}).get(key,[])
 except Exception:return []
entities=registry("core.entity_registry","entities")
devices=registry("core.device_registry","devices")
areas=registry("core.area_registry","areas")
labels=registry("core.label_registry","labels")
label_names={x.get("label_id",x.get("id")):x.get("name") for x in labels}
print("SECURITY_LIGHT_LABELS",json.dumps([{**{"id":k,"name":v}} for k,v in label_names.items() if re.search("security|porch|exterior|lighting|light",str(v),re.I)])[:5000],flush=True)
all_automation=yaml.safe_load((P/"automations.yaml").read_text()) or []
a=next((x for x in all_automation if x.get("alias")=="External Security Lights - Porch PIR"),None)
def safe(v):
 if isinstance(v,list):return [safe(x) for x in v]
 if isinstance(v,dict):
  return {k:("[REDACTED]" if re.search(r"(?i)secret|password|token|private_key|auth|bearer|encryption",k) else safe(val)) for k,val in v.items()}
 return v
print("PORCH_AUTOMATION_FULL",json.dumps(safe(a),default=str)[:12000],flush=True)
triggerid="binary_sensor.0xa4c138b3446c34e1_occupancy"
targets=["switch.0x84fd27fffe9ce438","switch.0xa4c138bda6ec8ea0"]
for eid in [triggerid,*targets]:
 e=next((x for x in entities if x.get("entity_id")==eid),None)
 print("EXACT_ENTITY",eid,json.dumps({"registry_found":bool(e),"entry":safe({k:e.get(k) for k in ("entity_id","name","original_name","platform","disabled_by","device_id","area_id","labels","unique_id","hidden_by")}) if e else None},default=str)[:1300],flush=True)
 if e:
  d=next((x for x in devices if x.get("id")==e.get("device_id")),None)
  print("DEVICE_DETAIL",eid,json.dumps({k:d.get(k) for k in ("name_by_user","name","manufacturer","model","area_id","labels","disabled_by")} if d else {})[:1000],flush=True)
for e in entities:
 if e.get("entity_id","").startswith(("binary_sensor.","switch.","light.")):
  text=" ".join(str(e.get(k,"")) for k in ("entity_id","original_name","name"))
  labstr=" ".join(str(label_names.get(y,y)) for y in (e.get("labels") or []))
  if re.search("porch|outdoor|external|security|front.?door|garage|dog.?s.? run|0xa4c138b3446c34e1",text+" "+labstr,re.I):
   print("CANDIDATE_ENTITY",json.dumps({"entity":e.get("entity_id"),"name":e.get("name") or e.get("original_name"),"platform":e.get("platform"),"disabled":e.get("disabled_by"),"labels":labstr,"area_id":e.get("area_id")},default=str)[:1200],flush=True)
for d in devices:
 s=" ".join(str(d.get(k,"")) for k in ("name","name_by_user","model"))
 if re.search("porch|0xa4c138b3446c34e1",s,re.I):
  print("CANDIDATE_DEVICE",json.dumps({k:d.get(k) for k in ("id","name","name_by_user","model","manufacturer","area_id","labels")} )[:1200],flush=True)
print("RESTORE_SNAPSHOT",flush=True)
try:
 restore=json.loads((P/".storage"/"core.restore_state").read_text()).get("data",[])
 if isinstance(restore,dict):restore=restore.get("states",[])
 for x in restore:
  s=x.get("state",{})
  if isinstance(s,dict) and s.get("entity_id") in [triggerid,*targets,"automation.external_security_lights_porch_pir"]:
   print("RESTORED_STATE",json.dumps({"entity":s.get("entity_id"),"state":s.get("state"),"last_changed":s.get("last_changed"),"last_updated":s.get("last_updated")},default=str),flush=True)
except Exception as err:print("RESTORE_ERR",type(err).__name__,flush=True)
path=P/"home-assistant_v2.db"
if path.is_file():
 try:
  db=sqlite3.connect("file:"+str(path)+"?mode=ro",uri=True,timeout=3)
  cur=db.cursor()
  for eid in [triggerid,*targets,"automation.external_security_lights_porch_pir"]:
   cur.execute("""SELECT s.state, s.last_updated_ts, s.last_changed_ts
   FROM states s JOIN states_meta m ON m.metadata_id=s.metadata_id
   WHERE m.entity_id=? ORDER BY s.state_id DESC LIMIT 3""",(eid,))
   print("RECENT_DB_STATES",eid,cur.fetchall(),flush=True)
  db.close()
 except Exception as e:print("DB_READ_ERROR",type(e).__name__,str(e)[:130],flush=True)
else:print("NO_RECORDER_SQLITE_FILE",flush=True)
print("PORCH_DETAIL_AUDIT_COMPLETE",flush=True)
'''
code="exec(__import__('base64').b64decode("+repr(base64.b64encode(SOURCE.encode()).decode())+"))"
def ssh(argv,timeout=30):
 p=subprocess.run(["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","nodeb",shlex.join(argv)],capture_output=True,text=True,timeout=timeout)
 if p.returncode:raise RuntimeError(p.stderr[-250:])
 return json.loads(p.stdout)
d=ssh(["qm","guest","exec","905","--","docker","exec","homeassistant","python3","-c",code])
for _ in range(25):
 if d.get("exited"):break
 time.sleep(.7)
 d=ssh(["qm","guest","exec-status","905",str(d["pid"])],20)
print("GUEST_EXIT_CODE",d.get("exitcode"),flush=True)
print((d.get("out-data") or "")[:35000],flush=True)
print("GUEST_ERROR",(d.get("err-data") or "")[:650],flush=True)
