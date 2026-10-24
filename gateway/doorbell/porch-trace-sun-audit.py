#!/usr/bin/env python3
"""Read-only porch PIR execution trace and sun gate evidence from HA-General."""
import subprocess,shlex,json,base64,time
SOURCE=r'''
from pathlib import Path
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
import json,sqlite3,re
P=Path("/config")
zone=ZoneInfo("Europe/London")
def uk(x):
 try:return datetime.fromtimestamp(float(x),timezone.utc).astimezone(zone).strftime("%Y-%m-%d %H:%M:%S %Z")
 except:return str(x)
p=P/".storage"/"trace.saved_traces"
if p.exists():
 try:
  d=json.loads(p.read_text())
  data=d.get("data",{})
  print("TRACE_FILE_STRUCTURE",type(data).__name__,list(data)[:15] if isinstance(data,dict) else len(data),flush=True)
  def walk(v,parent="",depth=0):
   if depth>5:return
   if isinstance(v,dict):
    if any("porch" in str(v.get(k,"")).lower() or "1792086505206" in str(v.get(k,"")) for k in ("item_id","entity_id","alias","name","id")) or "porch" in parent.lower() or "1792086505206" in parent:
     if "trace" in v or "config" in v:
      yield parent,v
    for k,val in v.items():
     if isinstance(val,(dict,list)):yield from walk(val,parent+"/"+str(k),depth+1)
   elif isinstance(v,list):
    for i,val in enumerate(v[:100]):
     if isinstance(val,(dict,list)):yield from walk(val,parent+"/"+str(i),depth+1)
  matches=list(walk(data))
  print("MATCHING_TRACE_RECORDS",len(matches),flush=True)
  for path,x in matches[-8:]:
   print("TRACE_META",json.dumps({"path":path,"item_id":x.get("item_id"),"run_id":x.get("run_id"),"timestamp":x.get("timestamp"),"state":x.get("state"),"last_step":x.get("last_step"),"error":str(x.get("error",""))[:190]},default=str)[:900],flush=True)
   tr=x.get("trace",{})
   if isinstance(tr,dict):
    for step,entries in tr.items():
     for entry in entries[:3] if isinstance(entries,list) else [entries]:
      if isinstance(entry,dict):
       result=entry.get("result")
       print("TRACE_STEP",json.dumps({"path":step,"timestamp":entry.get("timestamp"),"result":result,"error":entry.get("error")},default=str)[:1350],flush=True)
 except Exception as e:print("TRACE_AUDIT_ERROR",type(e).__name__,str(e)[:180],flush=True)
dbpath=P/"home-assistant_v2.db"
if dbpath.exists():
 try:
  db=sqlite3.connect("file:"+str(dbpath)+"?mode=ro",uri=True,timeout=2)
  cur=db.cursor()
  for eid in ("sun.sun","automation.external_security_lights_porch_pir","binary_sensor.0xa4c138b3446c34e1_occupancy"):
   cur.execute("""SELECT s.state,s.last_updated_ts
     FROM states s JOIN states_meta m ON s.metadata_id=m.metadata_id
     WHERE m.entity_id=? ORDER BY s.state_id DESC LIMIT 12""",(eid,))
   print("LAST_STATES",eid,json.dumps([{"state":st,"time":uk(ts)} for st,ts in cur.fetchall()]),flush=True)
  db.close()
 except Exception as e:print("STATE_DB_ERROR",type(e).__name__,str(e)[:180],flush=True)
print("PORCH_TRACE_SUN_AUDIT_COMPLETE",flush=True)
'''
code="exec(__import__('base64').b64decode("+repr(base64.b64encode(SOURCE.encode()).decode())+"))"
def ssh(argv,timeout=65):
 p=subprocess.run(["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","nodeb",shlex.join(argv)],capture_output=True,text=True,timeout=timeout)
 if p.returncode:raise RuntimeError(p.stderr[-220:])
 return json.loads(p.stdout)
d=ssh(["qm","guest","exec","905","--","docker","exec","homeassistant","python3","-c",code])
for _ in range(30):
 if d.get("exited"):break
 time.sleep(.7)
 d=ssh(["qm","guest","exec-status","905",str(d["pid"])],17)
print("GUEST_EXIT_CODE",d.get("exitcode"),flush=True)
print((d.get("out-data") or "")[:35000],flush=True)
print("GUEST_ERROR",(d.get("err-data") or "")[:500],flush=True)
