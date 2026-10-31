#!/usr/bin/env python3
"""Guarded live HA-General back-door trigger migration.
Edits only jns_backdoor_dogs_run_trigger_v1 in jns_garden_features_backdoor.yaml.
"""
from pathlib import Path
import copy,datetime,hashlib,json,os,stat,sys,tempfile,yaml

P=Path("/config/packages/jns_garden_features_backdoor.yaml")
ID="jns_backdoor_dogs_run_trigger_v1"
OLD="binary_sensor.backdoor_contact_sensor_door"
NEW="binary_sensor.backdoor_contact_switch_contact"

def fail(msg): raise RuntimeError(msg)
def sha(b): return hashlib.sha256(b).hexdigest()
def atomic(path,data):
    st=path.stat()
    fd,tmp=tempfile.mkstemp(prefix=".jns-backdoor-zigbee-",dir=str(path.parent))
    try:
        with os.fdopen(fd,"wb") as f:
            f.write(data); f.flush(); os.fsync(f.fileno())
        os.chown(tmp,st.st_uid,st.st_gid)
        os.chmod(tmp,stat.S_IMODE(st.st_mode))
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)

raw=P.read_bytes()
doc=yaml.safe_load(raw)
if not isinstance(doc,dict) or "automation" not in doc: fail("unexpected package shape")
autos=doc["automation"]
if not isinstance(autos,list): fail("automation list missing")
hits=[a for a in autos if isinstance(a,dict) and str(a.get("id"))==ID]
if len(hits)!=1: fail("target automation missing/duplicated")
orig=copy.deepcopy(hits[0])
a=hits[0]

# Guard current source mapping before modifying.
trigs=a.get("triggers",a.get("trigger"))
if not isinstance(trigs,list) or len(trigs)!=1: fail("unexpected trigger layout")
t=trigs[0]
if t.get("entity_id") not in (OLD,NEW): fail("unexpected existing back-door entity")
if t.get("from")!="off" or t.get("to")!="on": fail("unexpected contact state semantics")
t["entity_id"]=NEW

# Night-time only and no restart/extension while departure timer is already active.
a["conditions"]=[
    {"condition":"state","entity_id":"sun.sun","state":"below_horizon"},
    {"condition":"state","entity_id":"timer.jns_backdoor_dogs_run","state":"idle"},
]
a["description"]=(
    "JNS_BACKDOOR_ZIGBEE_V2 - Zigbee Backdoor Contact Switch opens Dogs Run "
    "security light at night only. Existing adjustable duration is preserved. "
    "If the Dogs Run timer is already active, a later/return door opening is ignored "
    "and does not restart or extend the countdown."
)
a["mode"]="single"

# Ensure ownership/duration mechanics remain unchanged.
blob=json.dumps(a,default=str)
for required in (
    "input_number.jns_backdoor_dogs_run_minutes",
    "timer.jns_backdoor_dogs_run",
    "switch.0x84fd27fffe9ce438",
    "input_boolean.jns_backdoor_dogs_preexisting",
):
    if required not in blob: fail("required existing behavior missing: "+required)

new=yaml.safe_dump(doc,sort_keys=False,allow_unicode=True,width=160).encode()
# semantic guard: every other automation remains exactly unchanged.
newdoc=yaml.safe_load(new)
old_other=[x for x in yaml.safe_load(raw)["automation"] if str(x.get("id"))!=ID]
new_other=[x for x in newdoc["automation"] if str(x.get("id"))!=ID]
if old_other!=new_other: fail("unrelated automation changed")

report={
 "target":str(P),
 "automation_id":ID,
 "old_trigger":OLD,
 "new_trigger":NEW,
 "night_only":True,
 "ignore_when_timer_active":True,
 "duration_helper":"input_number.jns_backdoor_dogs_run_minutes",
 "before_sha256":sha(raw),
 "after_sha256":sha(new),
}
print("JNS_BACKDOOR_ZIGBEE_PLAN "+json.dumps(report,sort_keys=True),flush=True)
if "--apply" not in sys.argv: raise SystemExit(0)

if P.read_bytes()!=raw: fail("concurrent package change")
stamp=datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
bkdir=Path("/config/.jns-backups")/("backdoor-zigbee-"+stamp)
bkdir.mkdir(parents=True,mode=0o700,exist_ok=False)
bk=bkdir/P.name
bk.write_bytes(raw); os.chmod(bk,0o600)
if sha(bk.read_bytes())!=sha(raw): fail("backup verification failed")
atomic(P,new)
if P.read_bytes()!=new: fail("post-write verification failed")
report["backup"]=str(bkdir)
print("JNS_BACKDOOR_ZIGBEE_APPLIED "+json.dumps(report,sort_keys=True),flush=True)
