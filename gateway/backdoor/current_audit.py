#!/usr/bin/env python3
import base64,json,shlex,subprocess,time
SRC=r'''
from pathlib import Path
import json,re,yaml,sqlite3,datetime
P=Path("/config")
def load(n,k):
    try:return json.loads((P/".storage"/n).read_text())["data"][k]
    except Exception:return []
ents=load("core.entity_registry","entities")
devs=load("core.device_registry","devices")
# candidate back-door/contact entities
cand=[]
for e in ents:
    txt=" ".join(str(e.get(k,"")) for k in ("entity_id","name","original_name"))
    if re.search(r"back.?door|rear.?door|door.*contact|contact.*door",txt,re.I):
        cand.append({"entity_id":e.get("entity_id"),"name":e.get("name") or e.get("original_name"),
                     "platform":e.get("platform"),"disabled":e.get("disabled_by"),"device_id":e.get("device_id")})
print("JNS_BACKDOOR_CANDIDATES="+json.dumps(cand,sort_keys=True),flush=True)

# live package/automations containing backdoor or dogs-run
rows=[]
for fp in [P/"automations.yaml",*sorted((P/"packages").glob("*.yaml"))]:
    if not fp.is_file(): continue
    try:d=yaml.safe_load(fp.read_text())
    except Exception: continue
    aa=d if isinstance(d,list) else d.get("automation",[]) if isinstance(d,dict) else []
    if isinstance(aa,dict): aa=list(aa.values())
    for a in aa if isinstance(aa,list) else []:
        if not isinstance(a,dict): continue
        blob=json.dumps(a,default=str)
        if re.search(r"back.?door|dogs?.?run|jns_backdoor",blob,re.I):
            rows.append({"file":fp.name,"id":a.get("id"),"alias":a.get("alias"),
                         "trigger":a.get("trigger",a.get("triggers")),
                         "condition":a.get("condition",a.get("conditions")),
                         "action":a.get("action",a.get("actions"))})
print("JNS_BACKDOOR_AUTOMATIONS="+json.dumps(rows,sort_keys=True,default=str),flush=True)

# package helper definitions around timer/duration
for fp in sorted((P/"packages").glob("*.yaml")):
    try:txt=fp.read_text()
    except Exception:continue
    if re.search(r"jns_backdoor|dogs?.?run",txt,re.I):
        print("JNS_BACKDOOR_PACKAGE_TEXT="+json.dumps({"file":fp.name,"text":txt[:16000]}),flush=True)

# recent state history for candidates + dogs run
ids=[x["entity_id"] for x in cand if x.get("entity_id")]
ids+=["switch.0x84fd27fffe9ce438","timer.jns_backdoor_dogs_run"]
db=P/"home-assistant_v2.db"
hist={}
if db.exists():
  c=sqlite3.connect("file:"+str(db)+"?mode=ro",uri=True,timeout=3);cur=c.cursor()
  for eid in ids:
    try:
      cur.execute("""SELECT s.state,s.last_updated_ts FROM states s
        JOIN states_meta m ON s.metadata_id=m.metadata_id
        WHERE m.entity_id=? ORDER BY s.state_id DESC LIMIT 8""",(eid,))
      hist[eid]=[{"state":st,"time":datetime.datetime.fromtimestamp(ts,datetime.timezone.utc).isoformat() if ts else None}
                 for st,ts in cur.fetchall()]
    except Exception:hist[eid]=[]
  c.close()
print("JNS_BACKDOOR_HISTORY="+json.dumps(hist,sort_keys=True),flush=True)
'''
enc=base64.b64encode(SRC.encode()).decode()
code="exec(__import__('base64').b64decode("+repr(enc)+"))"
def ssh(argv):
 p=subprocess.run(["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","nodeb",shlex.join(argv)],
                  capture_output=True,text=True,timeout=35)
 if p.returncode: raise RuntimeError(p.stderr[-500:])
 return json.loads(p.stdout)
d=ssh(["qm","guest","exec","905","--","docker","exec","homeassistant","python3","-c",code])
pid=d.get("pid")
for _ in range(60):
 if d.get("exited"):break
 time.sleep(.5)
 d=ssh(["qm","guest","exec-status","905",str(pid)])
print(d.get("out-data") or "")
if d.get("exitcode")!=0: raise SystemExit(d.get("exitcode") or 2)
