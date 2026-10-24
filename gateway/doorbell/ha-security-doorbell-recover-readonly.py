#!/usr/bin/env python3
"""JNS HA-Security local doorbell recovery, read-only and secrets-redacted."""
from pathlib import Path
import json, hashlib, re, datetime

BASE=Path("/homeassistant")
STORAGE=BASE/".storage"
RX=re.compile(r"door.?bell|ding.?dong|chime|sounder|bell.?button|kc868",re.I)
SECRET=re.compile(r"password|secret|token|api[_ -]?key|credential|encryption|private[_ -]?key|bearer|authorization",re.I)

def load_json(filename):
    p=STORAGE/filename
    if not p.is_file():
        print("FILE_MISSING",p,flush=True)
        return {}
    try: return json.loads(p.read_text())
    except Exception as e:
        print("JSON_READ_ERROR",filename,type(e).__name__,flush=True)
        return {}

def redact(v,depth=0):
    if depth>22:return "[DEPTH LIMIT]"
    if isinstance(v,dict):
        return {k:("[REDACTED]" if SECRET.search(str(k)) else redact(val,depth+1)) for k,val in v.items()}
    if isinstance(v,list):return [redact(item,depth+1) for item in v[:80]]
    if isinstance(v,str):return v[:1500]
    return v

def emit(prefix,obj,limit=20000):
    print(prefix,json.dumps(redact(obj),ensure_ascii=False,default=str,indent=2)[:limit],flush=True)

print("=== JNS HA-SECURITY DOORBELL RECOVERY (READ ONLY) ===",flush=True)
print("CLOCK",datetime.datetime.now(datetime.timezone.utc).isoformat(),flush=True)
p=BASE/"automations.yaml"
if p.exists():
    b=p.read_bytes()
    print("AUTOMATIONS_FILE","bytes",len(b),"sha256",hashlib.sha256(b).hexdigest(),"modified",datetime.datetime.fromtimestamp(p.stat().st_mtime,datetime.timezone.utc).isoformat(),flush=True)

doc=load_json("core.entity_registry")
entities=doc.get("data",{}).get("entities",[])
matches=[]
for e in entities:
    desc=" ".join(str(e.get(k,"")) for k in ("entity_id","name","original_name","unique_id"))
    if RX.search(desc):
        matches.append(e)
        emit("ENTITY",{"entity_id":e.get("entity_id"),"name":e.get("name") or e.get("original_name"),"unique_id":e.get("unique_id"),"platform":e.get("platform"),"device_id":e.get("device_id"),"disabled_by":e.get("disabled_by")},1200)
print("MATCHING_ENTITIES",len(matches),flush=True)
ids={e.get("entity_id") for e in matches}

document=load_json("trace.saved_traces")
data=document.get("data",{})
print("TRACE_STORE_TYPE",type(data).__name__,flush=True)
print("TRACE_STORE_TOP_KEYS",list(data.keys())[:25] if isinstance(data,dict) else "not-dict",flush=True)
seen=set()
found=[]

def walk(v,path="",depth=0):
    if depth>14:return
    if isinstance(v,dict):
        cfg=v.get("config")
        if isinstance(cfg,dict):
            alias=str(cfg.get("alias",""))
            item=str(v.get("item_id",""))
            loc=str(path)
            if RX.search(alias+" "+str(cfg.get("id",""))+" "+item+" "+loc):
                canon=json.dumps(cfg,sort_keys=True,default=str)
                digest=hashlib.sha256(canon.encode()).hexdigest()
                if digest not in seen:
                    seen.add(digest)
                    found.append((alias,item,path,cfg,v.get("timestamp"),v.get("last_step"),v.get("error")))
        for key,child in v.items():
            if isinstance(child,(list,dict)):walk(child,path+"/"+str(key),depth+1)
    elif isinstance(v,list):
        for index,child in enumerate(v[:300]):
            if isinstance(child,(list,dict)):walk(child,path+"/"+str(index),depth+1)

walk(data)
print("DOORBELL_CONFIG_SNAPSHOTS",len(found),flush=True)
for alias,item,path,cfg,ts,step,error in found[:12]:
    emit("TRACE_RECORD",{"alias":alias,"item_id":item,"path":path,"timestamp":ts,"last_step":step,"error":error},1700)
    emit("RECOVERED_AUTOMATION_CONFIG",cfg,23000)

if not found and isinstance(data,dict):
    print("TRACE_KEYS_MATCHING_DOORBELL",[k for k in data if RX.search(k)][:25],flush=True)

restore=load_json("core.restore_state")
state_data=restore.get("data",{})
states=state_data.get("states",[]) if isinstance(state_data,dict) else state_data
if isinstance(states,list):
    for rec in states:
        if not isinstance(rec,dict):continue
        st=rec.get("state",{})
        if not isinstance(st,dict):continue
        eid=st.get("entity_id","")
        if eid in ids:
            emit("RESTORED_ENTITY_STATE",{"entity_id":eid,"state":st.get("state"),"last_changed":st.get("last_changed"),"last_updated":st.get("last_updated")},650)

print("=== JNS READ-ONLY RECOVERY COMPLETE ===",flush=True)
