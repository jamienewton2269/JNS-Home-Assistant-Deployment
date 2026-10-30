#!/usr/bin/env python3
"""Guarded HA-General VM905 merged doorbell repair."""
import base64,json,pathlib,re,sys,time
sys.path.insert(0,"gateway/arrival_lighting")
from readiness_probe import ssh_host

ROOT=pathlib.Path("gateway/doorbell")
PKG=(ROOT/"jns_ha_general_doorbell_merged_v1.yaml").read_bytes()
TARGET="/config/packages/jns_ha_general_doorbell_merged_v1.yaml"

def guest(args,timeout=300):
    raw=ssh_host("nodeb",["qm","guest","exec","905","--",*args])
    d=json.loads(raw); deadline=time.monotonic()+timeout
    while not d.get("exited"):
        pid=d.get("pid")
        if not isinstance(pid,int): raise RuntimeError("QGA returned no PID; no blind retry")
        if time.monotonic()>deadline: raise RuntimeError("QGA operation still running pid="+str(pid))
        time.sleep(2)
        d=json.loads(ssh_host("nodeb",["qm","guest","exec-status","905",str(pid)]))
    return d

def py(source,args=(),timeout=160):
    code="exec(compile(__import__('base64').b64decode("+repr(base64.b64encode(source.encode()).decode())+"),'<jns-doorbell-repair>','exec'))"
    return guest(["docker","exec","homeassistant","python3","-c",code,*args],timeout)

PREFLIGHT=r'''
from pathlib import Path
import base64,json,sys,yaml
P=Path("/config"); target=Path(sys.argv[1]); payload=base64.b64decode(sys.argv[2])
wanted={"1792316952337","1792512302559","jns_security_doorbell_siren_safety_off_v1"}
# Required live entities and MQTT integration.
reg=json.loads((P/".storage/core.entity_registry").read_text())["data"]["entities"]
byid={e.get("entity_id"):e for e in reg}
for eid in ("binary_sensor.alarmpanel_kc868_a16_x15","switch.alarmpanel_kc868_a16_y01"):
    e=byid.get(eid)
    assert e and e.get("disabled_by") is None, "required live entity missing/disabled: "+eid
cfg=json.loads((P/".storage/core.config_entries").read_text())["data"]["entries"]
assert any(e.get("domain")=="mqtt" and e.get("disabled_by") is None for e in cfg),"MQTT integration unavailable"
# Existing exterior light consumer must remain present.
consumer=P/"packages/jns_doorbell_security_lighting.yaml"
assert consumer.is_file() and "jns/security/doorbell/press" in consumer.read_text(),"doorbell light consumer missing"
# Refuse duplicate active YAML definitions outside this target.
for fp in [P/"automations.yaml",*sorted((P/"packages").glob("*.yaml"))]:
    if fp==target or not fp.is_file(): continue
    try:d=yaml.safe_load(fp.read_text())
    except Exception: continue
    rows=d if isinstance(d,list) else d.get("automation",[]) if isinstance(d,dict) else []
    if isinstance(rows,dict): rows=list(rows.values())
    for a in rows if isinstance(rows,list) else []:
        if isinstance(a,dict) and str(a.get("id")) in wanted:
            raise AssertionError("duplicate automation id in "+str(fp))
# Validate staged package shape.
d=yaml.safe_load(payload)
rows=d.get("automation",[])
assert {str(x.get("id")) for x in rows}==wanted,"unexpected package automation IDs"
print("JNS_DOORBELL_REPAIR_PREFLIGHT_OK")
'''
APPLY=r'''
from pathlib import Path
import base64,datetime,hashlib,json,os,shutil,sys,tempfile
target=Path(sys.argv[1]); payload=base64.b64decode(sys.argv[2])
root=Path("/config"); stamp=datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
bkdir=root/".jns-backups"/("doorbell-merged-"+stamp); bkdir.mkdir(parents=True,mode=0o700)
before=None
if target.exists():
    before=target.read_bytes(); (bkdir/target.name).write_bytes(before)
fd,tmp=tempfile.mkstemp(prefix=".jns-doorbell-",dir=str(target.parent))
try:
    with os.fdopen(fd,"wb") as f:f.write(payload);f.flush();os.fsync(f.fileno())
    os.chmod(tmp,0o644);os.replace(tmp,target)
finally:
    if os.path.exists(tmp):os.unlink(tmp)
assert target.read_bytes()==payload
print("JNS_DOORBELL_REPAIR_APPLIED "+json.dumps({
 "backup":str(bkdir),"target":str(target),
 "before_sha256":hashlib.sha256(before).hexdigest() if before is not None else None,
 "after_sha256":hashlib.sha256(payload).hexdigest()}))
'''
RESTORE=r'''
from pathlib import Path
import hashlib,os,shutil,sys,tempfile
target=Path(sys.argv[1]); bkdir=Path(sys.argv[2]); expected=sys.argv[3]
assert target.exists() and hashlib.sha256(target.read_bytes()).hexdigest()==expected,"concurrent target change"
bk=bkdir/target.name
if bk.exists(): shutil.copy2(bk,target)
else: target.unlink()
print("JNS_DOORBELL_REPAIR_ROLLBACK_OK")
'''

def main():
    print("JNS_DOORBELL_REPAIR_BEGIN",flush=True)
    if "running" not in ssh_host("nodeb",["qm","status","905"]): raise RuntimeError("VM905 not running")
    b64=base64.b64encode(PKG).decode()
    r=py(PREFLIGHT,[TARGET,b64],120)
    print((r.get("out-data") or "")[-1500:],flush=True)
    if r.get("exitcode")!=0: raise RuntimeError("preflight failed: "+(r.get("err-data") or "")[-500:])
    r=py(APPLY,[TARGET,b64],120)
    out=r.get("out-data") or ""; print(out[-1800:],flush=True)
    if r.get("exitcode")!=0: raise RuntimeError("package apply failed: "+(r.get("err-data") or "")[-500:])
    m=re.search(r"JNS_DOORBELL_REPAIR_APPLIED (\{[^\n]+\})",out)
    if not m: raise RuntimeError("missing apply attestation")
    rec=json.loads(m.group(1))
    try:
        chk=guest(["ha","core","check"],300)
        print("JNS_DOORBELL_HA_CHECK exit="+str(chk.get("exitcode")),flush=True)
        if chk.get("out-data"): print((chk.get("out-data") or "")[-1600:],flush=True)
        if chk.get("exitcode")!=0: raise RuntimeError("HA config check failed")
    except BaseException:
        rr=py(RESTORE,[TARGET,rec["backup"],rec["after_sha256"]],120)
        print((rr.get("out-data") or "")[-500:],flush=True)
        raise
    # Package automation definitions: one guarded Core restart gives deterministic reload/initial_state.
    before=guest(["docker","inspect","--format","{{.State.StartedAt}}","homeassistant"],30).get("out-data","").strip()
    rr=guest(["ha","core","restart"],300)
    if rr.get("exitcode")!=0: raise RuntimeError("Core restart command failed")
    ok=False
    for _ in range(45):
        time.sleep(3)
        try:
            cur=guest(["docker","inspect","--format","{{.State.Running}} {{.State.StartedAt}}","homeassistant"],30)
            state=(cur.get("out-data") or "").strip()
            if state.startswith("true ") and before not in state:
                ok=True;break
        except Exception:pass
    if not ok: raise RuntimeError("Core restart not confirmed")
    print("JNS_DOORBELL_REPAIR_DEPLOYED_OK",flush=True)
    print("trigger=binary_sensor.alarmpanel_kc868_a16_x15",flush=True)
    print("sounder=switch.alarmpanel_kc868_a16_y01",flush=True)
    print("mqtt_topic=jns/security/doorbell/press",flush=True)

if __name__=="__main__":
    try:main()
    except Exception as e:
        print("JNS_DOORBELL_REPAIR_BLOCKED "+type(e).__name__+": "+str(e)[:500],flush=True)
        raise SystemExit(2)
