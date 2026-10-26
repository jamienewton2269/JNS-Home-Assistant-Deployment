#!/usr/bin/env python3
"""Second-level incident evidence: automation triggers and physical output mappings.
Read-only, no actuation or config changes. Does NOT print secrets/IPs/tokens.
"""
import base64,json,shlex,subprocess,time
PAYLOAD=r'''
import os,json,re,sqlite3,datetime,socket,urllib.request,urllib.error
from pathlib import Path
import yaml
P=Path("/config")
def sanitize(v,depth=0):
 if depth>9:return "(deep)"
 if isinstance(v,list):return [sanitize(x,depth+1) for x in v[:22]]
 if isinstance(v,dict):
  allow={"trigger","triggers","platform","entity_id","from","to","topic","payload","id","event_type",
         "condition","conditions","action","actions","service","target","state","for","below","above","at",
         "after","before","mode","choose","sequence","default","delay","duration","initial_state","enabled","alias"}
  return {k:sanitize(x,depth+1) for k,x in v.items() if k in allow}
 if isinstance(v,str):return v[:160]
 return v
TARGETS={
 "automation.doorbell_sounder_on_schedule",
 "automation.jns_security_publish_doorbell_press",
 "automation.jns_security_doorbell_sounder_safety_off",
 "automation.jns_doorbell_mqtt_night_security_lighting",
 "automation.external_security_lights_porch_pir",
 "binary_sensor.alarmpanel_kc868_a16_x15",
 "switch.alarmpanel_kc868_a16_y01",
 "siren.alarmpanel_kc868_a16_y01",
 "binary_sensor.0xa4c138b3446c34e1_occupancy",
 "switch.0x84fd27fffe9ce438",
 "switch.0xa4c138bda6ec8ea0",
 "light.0x847127fffe28965b",
 "switch.front_door_exterior_light",
 "binary_sensor.porch_motion_sensor_occupancy",
}
out={"vm_data_readonly":True,"target_history":{},"yaml":[],
    "core_api_available":False,"esphome_api_reachable":None}
p=P/"packages"
for source in (P/"automations.yaml",p/"jns_security_doorbell_recovery.yaml",p/"jns_doorbell_security_lighting.yaml",P/"packages"/"jns_garden_features_backdoor.yaml"):
 if not source.is_file():continue
 try:
  doc=yaml.safe_load(source.read_text())
  autos=doc if isinstance(doc,list) else doc.get("automation",[]) if isinstance(doc,dict) else []
  if isinstance(autos,dict):autos=list(autos.values())
  for a in autos:
   if not isinstance(a,dict):continue
   if re.search(r"(?i)doorbell|security.?lights|porch pir|dogs run",str(a.get("alias",""))):
    out["yaml"].append({"file":source.name,"config":sanitize(a)})
 except Exception as e:out.setdefault("yaml_parse_errors",[]).append({"file":source.name,"reason":type(e).__name__})
# Identify native API host from protected integration data but only test socket, don't print host.
try:
 entries=json.loads((P/".storage/core.config_entries").read_text()).get("data",{}).get("entries",[])
 esps=[e for e in entries if e.get("domain")=="esphome" and not e.get("disabled_by")]
 if esps:
  host=esps[0].get("data",{}).get("host")
  if isinstance(host,str) and host and len(host)<256:
   try:
    with socket.create_connection((host,6053),timeout=4):out["esphome_api_reachable"]=True
   except OSError:out["esphome_api_reachable"]=False
except Exception:pass
# Latest DB states + exact date, automation last_triggered and friendly_name attributes only
db=P/"home-assistant_v2.db"
if db.is_file():
 try:
  sql=sqlite3.connect("file:"+str(db)+"?mode=ro",uri=True,timeout=4)
  cur=sql.cursor()
  for eid in sorted(TARGETS):
   try:
    cur.execute("""SELECT s.state,s.last_updated_ts,sa.shared_attrs
                  FROM states s JOIN states_meta m ON s.metadata_id=m.metadata_id
                  LEFT JOIN state_attributes sa ON sa.attributes_id=s.attributes_id
                  WHERE m.entity_id=? ORDER BY s.state_id DESC LIMIT 5""",(eid,))
    rows=[]
    for state,ts,attrs in cur.fetchall():
     item={"state":state,"utc":datetime.datetime.fromtimestamp(ts,datetime.timezone.utc).isoformat() if isinstance(ts,(int,float)) else "unknown"}
     try:
      aa=json.loads(attrs or "{}")
      if isinstance(aa,dict):
       for k in ("last_triggered","current","max","restored","friendly_name"):
        if k in aa:item[k]=str(aa[k])[:140]
     except ValueError:pass
     rows.append(item)
    if rows:out["target_history"][eid]=rows
   except sqlite3.Error:pass
  sql.close()
 except Exception as e:out["sqlite_read_error"]=type(e).__name__
# Supervisor API when accessible from Core container, token remains entirely local
token=os.environ.get("SUPERVISOR_TOKEN")
if token:
 try:
  result=[]
  for entity in sorted(TARGETS):
   req=urllib.request.Request("http://supervisor/core/api/states/"+entity,
                              headers={"Authorization":"Bearer "+token})
   try:
    with urllib.request.urlopen(req,timeout=3) as h:x=json.load(h)
    item={"id":entity,"state":x.get("state"),"updated":x.get("last_updated")}
    if entity.startswith("automation."):item["last_triggered"]=x.get("attributes",{}).get("last_triggered")
    result.append(item)
   except urllib.error.HTTPError as e:
    if e.code not in (404,401,403):pass
  out["core_api_available"]=True
  out["live_states"]=result
 except Exception:out["core_api_available"]=False
# Saved automation trace result summaries without dumping potential secrets.
try:
 traces=json.loads((P/".storage/trace.saved_traces").read_text()).get("data",{})
 tracehits=[]
 def walk(obj,depth=0):
  if depth>6:return
  if isinstance(obj,dict):
   uid=str(obj.get("item_id",""))
   if uid in ("1792316952337","1792512302559","1792086505206","jns_doorbell_security_mqtt_20261020"):
    tracehits.append({"item":uid,"timestamp":obj.get("timestamp"),"last_step":obj.get("last_step"),
         "error_code":str(obj.get("error",""))[:130]})
   for v in obj.values():
    if isinstance(v,(list,dict)):walk(v,depth+1)
  elif isinstance(obj,list):
   for v in obj[:50]:walk(v,depth+1)
 walk(traces)
 out["stored_automation_traces"]=tracehits[:15]
except Exception:pass
print("JNS_CAUSAL_EVIDENCE="+json.dumps(out,sort_keys=True,default=str),flush=True)
'''
def ssh(host,cmd,timeout=35):
 try:p=subprocess.run(["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=6",host,shlex.join(cmd)],
   text=True,capture_output=True,timeout=timeout)
 except (OSError,subprocess.TimeoutExpired):return None
 return p.stdout if p.returncode==0 else None
def inspect(host,vm):
 enc=base64.b64encode(PAYLOAD.encode()).decode()
 cmd=["qm","guest","exec",str(vm),"--","docker","exec","homeassistant","python3","-c",
 "exec(__import__('base64').b64decode('"+enc+"'))"]
 s=ssh(host,cmd,38)
 if not s:return {"status":"guest_agent_unavailable"}
 try:x=json.loads(s)
 except ValueError:return {"status":"invalid_agent_reply"}
 for _ in range(30):
  if x.get("exited"):break
  if not x.get("pid"):break
  time.sleep(.5)
  raw=ssh(host,["qm","guest","exec-status",str(vm),str(x["pid"])],12)
  if not raw:break
  try:x=json.loads(raw)
  except ValueError:break
 if not x.get("exited") or x.get("exitcode")!=0:return {"status":"guest_error","exitcode":x.get("exitcode")}
 hits=[r.split("=",1)[1] for r in (x.get("out-data") or "").splitlines() if r.startswith("JNS_CAUSAL_EVIDENCE=")]
 try:return {"status":"ok",**json.loads(hits[-1])}
 except (ValueError,IndexError):return {"status":"parse_fail"}
for host,vm in (("nodea",906),("nodeb",905)):
 print("JNS_CAUSAL_VM"+str(vm)+"="+json.dumps(inspect(host,vm),sort_keys=True),flush=True)
print("JNS_CAUSAL_AUDIT_READONLY=yes",flush=True)
