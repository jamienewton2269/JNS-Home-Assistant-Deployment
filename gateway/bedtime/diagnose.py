#!/usr/bin/env python3
"""Read-only bedtime / morning reset / Garden String Lights audit on HA-General VM905.
Intentionally does not send commands to lights or alter HA configuration.
Outputs only relevant entity names, automation structure and bounded history.
"""
import base64, json, sys, time
sys.path.insert(0,"gateway/arrival_lighting")
from readiness_probe import ssh_host

PROBE=r'''
import collections, datetime, json, os, pathlib, re, sqlite3, stat, urllib.error, urllib.request
from zoneinfo import ZoneInfo
try:
 import yaml
except ImportError:
 yaml=None
ROOT=pathlib.Path("/config")
STOR=ROOT/".storage"
RX=re.compile(r"garden.{0,20}string|string.{0,20}light|bedtime|bed.?time|goodnight|morning|catch.?all|night.?reset",re.I)
STRINGS=re.compile(r"garden.{0,20}string|string.{0,20}light",re.I)
AUTO=re.compile(r"bedtime|bed.?time|goodnight|morning|catch.?all|night.?reset|general.*lux|dusk|light.*control",re.I)
out={"audit_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),"node":"nodeb","vmid":905,"mode":"read_only"}
def load(name,key):
 try:return json.loads((STOR/name).read_text())["data"][key]
 except Exception:return []
es=load("core.entity_registry","entities")
devs={d.get("id"):d for d in load("core.device_registry","devices")}
entities=[]
for e in es:
 eid=e.get("entity_id") or ""
 name=str(e.get("name") or e.get("original_name") or "")
 d=devs.get(e.get("device_id"),{})
 dn=str(d.get("name_by_user") or d.get("name") or "")
 if STRINGS.search(" ".join((eid,name,dn))):
  entities.append({"id":eid,"name":name[:110],"device_name":dn[:110],"platform":e.get("platform"),"disabled":e.get("disabled_by"),"area_id":e.get("area_id"),"labels":e.get("labels",[])})
out["garden_string_registry"]=entities[:30]
target_ids={e["id"] for e in entities if e["id"].startswith(("light.","switch."))}
out["target_ids"]=sorted(target_ids)
auto=[]
scenes=[]
for p in [ROOT/"automations.yaml",ROOT/"scripts.yaml",ROOT/"scenes.yaml",*sorted((ROOT/"packages").glob("*.yaml"))]:
 if not p.is_file() or yaml is None:continue
 try:v=yaml.safe_load(p.read_text()) or {}
 except Exception as ex:
  out.setdefault("parse_errors",[]).append([p.name,type(ex).__name__]);continue
 def getrows(v,key):
  if key=="automation" and isinstance(v,list):return v
  if key=="script" and p.name=="scripts.yaml" and isinstance(v,dict):return [{"alias":k,"sequence":x.get("sequence",[]) if isinstance(x,dict) else x} for k,x in v.items()]
  if isinstance(v,dict):
   t=v.get(key,[])
   return t if isinstance(t,list) else ([dict(item,alias=item.get('alias',k)) for k,item in t.items() if isinstance(item,dict)] if isinstance(t,dict) else [])
  return []
 for kind in ("automation","script"):
  for row in getrows(v,kind):
   if not isinstance(row,dict):continue
   name=str(row.get("alias",""))
   rid=str(row.get("id",""))
   data=json.dumps(row,default=str)
   if not (AUTO.search(name+" "+rid) or STRINGS.search(data)):continue
   # No wholesale YAML export. Extract action types, entity targets and structural conditions.
   def extract(obj,key,limit=100):
    found=[]
    def walk(x):
     if len(found)>=limit:return
     if isinstance(x,dict):
      for k,v in x.items():
       if k==key:
        values=v if isinstance(v,list) else [v]
        for it in values:
         if isinstance(it,str):found.append(it[:170])
       walk(v)
     elif isinstance(x,list):
      for y in x:walk(y)
    walk(obj);return list(dict.fromkeys(found))[:limit]
   auto.append({"path":str(p.relative_to(ROOT)),"kind":kind,"alias":name[:150],"id":rid[:90],
    "disabled_by_initial_state":row.get("initial_state"),
    "triggers":extract(row.get("triggers",row.get("trigger",[])),"at")[:8],
    "actions":list(dict.fromkeys(extract(row,"action")+extract(row,"service")))[:35],
    "entity_refs":list(dict.fromkeys(extract(row,"entity_id")))[:70],
    "target_templates":list(dict.fromkeys(extract(row,"value_template")+extract(row,"entity_id")))[:75],
    "condition_types":list(dict.fromkeys(extract(row,"condition")))[:15],
    "mentions_garden_string":bool(STRINGS.search(data)),
    "has_turn_off":bool(re.search(r"turn_off",data)),
    "has_sunrise":bool(re.search(r"sunrise|06:|07:|08:|morning",data,re.I))})
out["matching_automations_and_scripts"]=auto[:90]
out["candidate_automation_count"]=len(auto)
# Readonly Home Assistant API on loopback. Token never appears in output, logs or argv.
def api_states():
 path=STOR.parent/".jns-steward/ha_general_api.token"
 if not path.is_file() or path.is_symlink():return {"status":"no_local_steward_auth"}
 st=path.stat()
 if st.st_uid!=0 or stat.S_IMODE(st.st_mode)!=0o600:return {"status":"local_steward_auth_permissions_invalid"}
 tok=path.read_text().strip()
 if not 64<=len(tok)<=1024:return {"status":"local_steward_auth_invalid_length"}
 req=urllib.request.Request("http://127.0.0.1/api/states",headers={"Authorization":"Bearer "+tok,"Accept":"application/json"})
 try:
  opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
  with opener.open(req,timeout=10) as res:states=json.loads(res.read(4000000))
 except urllib.error.HTTPError as ex:return {"status":"HTTP_"+str(ex.code)}
 except Exception as ex:return {"status":type(ex).__name__}
 observed=[]
 for s in states:
  eid=s.get("entity_id","");attrs=s.get("attributes",{}) or {}
  if eid in target_ids or (eid.startswith("automation.") and AUTO.search(eid+" "+str(attrs.get("friendly_name","")))):
   observed.append({"entity":eid,"state":s.get("state"),"last_changed":s.get("last_changed"),
     "last_updated":s.get("last_updated"),"last_triggered":attrs.get("last_triggered"),
     "friendly_name":str(attrs.get("friendly_name",""))[:140]})
 return {"status":"ok","matching":observed[:100],"count":len(observed)}
out["live_ha_states"]=api_states()
# HA recorder: last 48h only. State changes are evidence; a missing change is not proof of no service call.
db=ROOT/"home-assistant_v2.db"
if db.exists():
 try:
  uri="file:"+str(db)+"?mode=ro"
  con=sqlite3.connect(uri,uri=True,timeout=3)
  con.execute("PRAGMA query_only=ON")
  cutoff=(datetime.datetime.now(datetime.timezone.utc)-datetime.timedelta(hours=48)).timestamp()
  tables={x[0] for x in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
  hist=[]
  if "states_meta" in tables and "states" in tables:
   candidates={r[0] for r in con.execute("SELECT entity_id FROM states_meta WHERE lower(entity_id) LIKE '%garden%' OR lower(entity_id) LIKE '%string%' OR lower(entity_id) LIKE 'automation.%bedtime%' OR lower(entity_id) LIKE 'automation.%morning%'")}
   candidates.update(target_ids)
   for eid in sorted(candidates)[:50]:
    if not (eid in target_ids or STRINGS.search(eid) or AUTO.search(eid)):continue
    rows=con.execute("SELECT s.state, s.last_updated_ts, s.last_changed_ts FROM states s JOIN states_meta m ON m.metadata_id=s.metadata_id WHERE m.entity_id=? AND s.last_updated_ts>=? ORDER BY s.last_updated_ts DESC LIMIT 45",(eid,cutoff)).fetchall()
    if rows:hist.append({"entity":eid,"rows":[{"state":state,"at_utc":datetime.datetime.fromtimestamp(t,datetime.timezone.utc).isoformat() if t else None} for state,t,_ in rows[:45]]})
  out["recorder_history"]=hist[:45]
  out["recorder_tables"]=sorted(t for t in tables if t in ("events","event_types","event_data","states","states_meta"))
  con.close()
 except Exception as ex:out["recorder_error"]=type(ex).__name__
# Saved traces: expose only automation identifiers, when available; never raw trace variables.
tp=STOR/"trace.saved_traces"
if tp.exists():
 try:
  tr=json.loads(tp.read_text()).get("data",{})
  if isinstance(tr,dict):
   out["recent_trace_keys"]=[str(k) for k in tr if AUTO.search(str(k))][:30]
 except Exception as ex:out["trace_error"]=type(ex).__name__
# A bounded, redacted count of relevant Core warnings or errors.
lp=ROOT/"home-assistant.log"
if lp.exists():
 lines=lp.read_text(errors="replace").splitlines()[-15000:]
 matching=[s for s in lines if RX.search(s) and (" ERROR " in s or " WARNING " in s)]
 out["relevant_warning_error_count"]=len(matching)
 out["relevant_warning_error_components"]=[(re.search(r"\[([a-zA-Z0-9_.-]+)\]",x).group(1) if re.search(r"\[([a-zA-Z0-9_.-]+)\]",x) else "unknown") for x in matching[-20:]]
# Targeted second-stage evidence: the bedtime selectors and actual bedtime input transitions.
out["bedtime_rule_details"]={}
for basename in ("jns_bedtime_controller.yaml","outdoor_environment.yaml"):
 path=ROOT/"packages"/basename
 if not path.exists() or yaml is None: continue
 try:
  d=yaml.safe_load(path.read_text())
  if not isinstance(d,dict):continue
  chosen={}
  for key in ("script","automation"):
   group=d.get(key,{})
   if isinstance(group,dict):
    for name,item in group.items():
     if re.search(r"bedtime|morning|evening_lights_off|outdoor_daylight",name,re.I):
      chosen[name]=yaml.safe_dump(item,sort_keys=False,allow_unicode=True,width=130)[:18000]
   elif isinstance(group,list):
    for item in group:
     if isinstance(item,dict) and AUTO.search(str(item.get("alias",""))):
      chosen[str(item.get("alias",""))]=yaml.safe_dump(item,sort_keys=False,width=130)[:5500]
  out["bedtime_rule_details"][basename]=chosen
 except Exception as ex:
  out["bedtime_rule_details"][basename]={"error":type(ex).__name__}
# Lightweight recorder history of the activation and the staged script.
try:
 con=sqlite3.connect("file:"+str(db)+"?mode=ro",uri=True,timeout=3)
 con.execute("PRAGMA query_only=ON")
 more={}
 for eid in ("input_boolean.general_bedtime_mode","script.jns_bedtime_shutdown","script.general_evening_lights_off","sun.sun","input_boolean.jns_bedtime_snapshot_valid","automation.general_shared_lux_progressive_control"):
  rows=con.execute("SELECT s.state,s.last_updated_ts FROM states s JOIN states_meta m ON m.metadata_id=s.metadata_id WHERE m.entity_id=? AND s.last_updated_ts>=? ORDER BY s.last_updated_ts DESC LIMIT 28",(eid,cutoff)).fetchall()
  more[eid]=[{"state":state,"at_utc":datetime.datetime.fromtimestamp(t,datetime.timezone.utc).isoformat() if t else None} for state,t in rows]
 out["bedtime_runtime_history"]=more
 con.close()
except Exception as ex:out["bedtime_runtime_history_error"]=type(ex).__name__
print(json.dumps(out,ensure_ascii=False,default=str,separators=(",",":")))
'''
def ssh(args):
 return ssh_host("nodeb",args)
print("JNS_BEDTIME_GARDEN_STRING_READONLY_BEGIN",flush=True)
print("UTC",time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),flush=True)
try:
 status=ssh(["qm","status","905"]).strip()
 print("VM905_STATUS",status,flush=True)
 if "running" not in status:raise RuntimeError("VM905 stopped")
 code="import base64,traceback\ntry:\n exec(base64.b64decode('"+base64.b64encode(PROBE.encode()).decode()+"'))\nexcept Exception as ex:\n print('JNS_GUEST_EXCEPTION',type(ex).__name__,str(ex)[:280],flush=True)\n print('JNS_GUEST_TRACE_TAIL',repr(traceback.format_exc().splitlines()[-2:]),flush=True)\n raise SystemExit(2)\n"
 response=json.loads(ssh(["qm","guest","exec","905","--","docker","exec","homeassistant","python3","-c",code]))
 deadline=time.monotonic()+110
 while not response.get("exited"):
  if not isinstance(response.get("pid"),int):raise RuntimeError("QGA has no PID")
  if time.monotonic()>deadline:raise RuntimeError("QGA timeout; no blind retry")
  time.sleep(2)
  response=json.loads(ssh(["qm","guest","exec-status","905",str(response["pid"])]))
 print("GUEST_EXIT_CODE",response.get("exitcode"),flush=True)
 if response.get("exitcode")!=0:raise RuntimeError("guest probe non-zero: "+str(response.get("err-data") or "")[-1250:])
 print("JNS_BEDTIME_GARDEN_STRING_AUDIT",response.get("out-data","")[:60000],flush=True)
except Exception as ex:
 print("JNS_BEDTIME_GARDEN_STRING_BLOCKED",type(ex).__name__,str(ex)[:200],flush=True)
 raise SystemExit(2)
print("JNS_BEDTIME_GARDEN_STRING_READONLY_END",flush=True)
