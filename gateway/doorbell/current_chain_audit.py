#!/usr/bin/env python3
import base64,json,shlex,subprocess,time
SOURCE=r'''
from pathlib import Path
import json,re,sqlite3,datetime,yaml
P=Path("/config")
def load(name,key):
    try:return json.loads((P/".storage"/name).read_text()).get("data",{}).get(key,[])
    except Exception:return []
ents=load("core.entity_registry","entities")
matches=[]
for e in ents:
    nm=(e.get("name") or e.get("original_name") or "")
    eid=e.get("entity_id","")
    if re.search(r"door.?bell.*push|push.*door.?bell|doorbell sounder|kc868.*x15|kc868.*y01",nm+" "+eid,re.I):
        matches.append({"entity_id":eid,"name":nm,"platform":e.get("platform"),"disabled":e.get("disabled_by")})
print("JNS_DOORBELL_TARGET_ENTITIES="+json.dumps(matches,sort_keys=True),flush=True)

# Exact relevant automations from YAML sources.
wanted={"1792316952337","1792512302559","jns_security_doorbell_siren_safety_off_v1",
        "jns_doorbell_security_mqtt_20261020","jns_doorbell_security_release_20261020"}
rows=[]
for fp in [P/"automations.yaml",*sorted((P/"packages").glob("*.yaml"))]:
    if not fp.exists():continue
    try:d=yaml.safe_load(fp.read_text())
    except Exception:continue
    aa=d if isinstance(d,list) else d.get("automation",[]) if isinstance(d,dict) else []
    if isinstance(aa,dict):aa=list(aa.values())
    for a in aa if isinstance(aa,list) else []:
        if isinstance(a,dict) and (str(a.get("id")) in wanted or re.search(r"doorbell.*dingdong|publish doorbell press|doorbell sounder safety",str(a.get("alias","")),re.I)):
            rows.append({"file":fp.name,"id":a.get("id"),"alias":a.get("alias"),
                         "triggers":a.get("triggers",a.get("trigger")),
                         "conditions":a.get("conditions",a.get("condition")),
                         "actions":a.get("actions",a.get("action"))})
print("JNS_DOORBELL_AUTOMATIONS="+json.dumps(rows,sort_keys=True,default=str),flush=True)

# Recent recorder history for exact matched entities and automation entities.
ids=[x["entity_id"] for x in matches]
ids += ["automation.doorbell_dingdong_7am_till_11pm",
        "automation.jns_security_publish_doorbell_press",
        "automation.jns_security_doorbell_sounder_safety_off",
        "automation.jns_doorbell_mqtt_night_security_lighting",
        "switch.0xa4c138bda6ec8ea0","switch.0x84fd27fffe9ce438"]
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
print("JNS_DOORBELL_RECENT_HISTORY="+json.dumps(hist,sort_keys=True),flush=True)
'''
code="exec(__import__('base64').b64decode("+repr(base64.b64encode(SOURCE.encode()).decode())+"))"
def ssh(argv):
    p=subprocess.run(["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","nodeb",shlex.join(argv)],
                     capture_output=True,text=True,timeout=35)
    if p.returncode: raise RuntimeError(p.stderr[-500:])
    return json.loads(p.stdout)
r=ssh(["qm","guest","exec","905","--","docker","exec","homeassistant","python3","-c",code])
for _ in range(50):
    if r.get("exited"):break
    time.sleep(.5)
    r=ssh(["qm","guest","exec-status","905",str(r["pid"])])
print(r.get("out-data") or "",flush=True)
if r.get("exitcode")!=0: raise SystemExit(r.get("exitcode") or 2)
