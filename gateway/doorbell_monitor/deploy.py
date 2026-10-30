#!/usr/bin/env python3
"""Transactional deployment of native HA-General doorbell health monitor."""
import base64,json,pathlib,re,sys,time
sys.path.insert(0,"gateway/arrival_lighting")
from readiness_probe import ssh_host

ROOT=pathlib.Path("gateway/doorbell_monitor")
PKG=(ROOT/"jns_doorbell_health_monitor_v1.yaml").read_bytes()
TARGET="/config/packages/jns_doorbell_health_monitor_v1.yaml"

def guest(args,timeout=300):
    d=json.loads(ssh_host("nodeb",["qm","guest","exec","905","--",*args]))
    pid=d.get("pid")
    if not d.get("exited") and not isinstance(pid,int):
        raise RuntimeError("QGA returned no PID")
    deadline=time.monotonic()+timeout
    while not d.get("exited"):
        if time.monotonic()>deadline: raise RuntimeError("QGA timeout pid="+str(pid))
        time.sleep(2)
        d=json.loads(ssh_host("nodeb",["qm","guest","exec-status","905",str(pid)]))
    return d

def py(source,args=(),timeout=120):
    code="exec(compile(__import__('base64').b64decode("+repr(base64.b64encode(source.encode()).decode())+"),'<jns-doorbell-monitor>','exec'))"
    return guest(["docker","exec","homeassistant","python3","-c",code,*args],timeout)

PREFLIGHT=r'''
from pathlib import Path
import base64,json,sys,yaml
P=Path("/config"); target=Path(sys.argv[1]); payload=base64.b64decode(sys.argv[2])
reg=json.loads((P/".storage/core.entity_registry").read_text())["data"]["entities"]
byid={e.get("entity_id"):e for e in reg}
for eid in (
 "binary_sensor.alarmpanel_kc868_a16_x15",
 "switch.alarmpanel_kc868_a16_y01",
 "automation.doorbell_dingdong_7am_till_11pm",
 "automation.jns_security_publish_doorbell_press",
 "automation.jns_security_doorbell_sounder_safety_off",
 "automation.jns_doorbell_mqtt_night_security_lighting",
 "timer.jns_doorbell_security_lighting"):
    e=byid.get(eid)
    assert e and e.get("disabled_by") is None, "required entity missing/disabled: "+eid
# Ensure repaired source package remains present.
src=P/"packages/jns_ha_general_doorbell_merged_v1.yaml"
assert src.is_file(),"repaired doorbell package missing"
d=yaml.safe_load(payload)
assert isinstance(d,dict) and "automation" in d and "template" in d,"invalid monitor package"
ids={str(a.get("id")) for a in d["automation"]}
assert ids=={
 "jns_doorbell_health_static_monitor_v1",
 "jns_doorbell_health_press_watchdog_v1",
 "jns_doorbell_health_recovery_clear_v1"},"unexpected automation IDs"
print("JNS_DOORBELL_MONITOR_PREFLIGHT_OK")
'''
APPLY=r'''
from pathlib import Path
import base64,datetime,hashlib,json,os,shutil,sys,tempfile
target=Path(sys.argv[1]); payload=base64.b64decode(sys.argv[2]); root=Path("/config")
stamp=datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
bkdir=root/".jns-backups"/("doorbell-monitor-"+stamp); bkdir.mkdir(parents=True,mode=0o700)
before=target.read_bytes() if target.exists() else None
if before is not None:(bkdir/target.name).write_bytes(before)
fd,tmp=tempfile.mkstemp(prefix=".jns-doorbell-monitor-",dir=str(target.parent))
try:
  with os.fdopen(fd,"wb") as f:f.write(payload);f.flush();os.fsync(f.fileno())
  os.chmod(tmp,0o644);os.replace(tmp,target)
finally:
  if os.path.exists(tmp):os.unlink(tmp)
assert target.read_bytes()==payload
print("JNS_DOORBELL_MONITOR_APPLIED "+json.dumps({
 "backup":str(bkdir),"target":str(target),
 "before_sha256":hashlib.sha256(before).hexdigest() if before else None,
 "after_sha256":hashlib.sha256(payload).hexdigest()}))
'''
RESTORE=r'''
from pathlib import Path
import hashlib,sys,shutil
target=Path(sys.argv[1]); bkdir=Path(sys.argv[2]); expected=sys.argv[3]
assert target.exists() and hashlib.sha256(target.read_bytes()).hexdigest()==expected
bk=bkdir/target.name
if bk.exists():shutil.copy2(bk,target)
else:target.unlink()
print("JNS_DOORBELL_MONITOR_ROLLBACK_OK")
'''

def main():
    print("JNS_DOORBELL_MONITOR_DEPLOY_BEGIN",flush=True)
    if "running" not in ssh_host("nodeb",["qm","status","905"]): raise RuntimeError("VM905 not running")
    b64=base64.b64encode(PKG).decode()
    r=py(PREFLIGHT,[TARGET,b64])
    print((r.get("out-data") or "")[-1200:],flush=True)
    if r.get("exitcode")!=0: raise RuntimeError("preflight failed "+(r.get("err-data") or "")[-500:])
    r=py(APPLY,[TARGET,b64])
    out=r.get("out-data") or ""; print(out[-1500:],flush=True)
    if r.get("exitcode")!=0: raise RuntimeError("apply failed "+(r.get("err-data") or "")[-500:])
    m=re.search(r"JNS_DOORBELL_MONITOR_APPLIED (\{[^\n]+\})",out)
    if not m: raise RuntimeError("missing apply attestation")
    rec=json.loads(m.group(1))
    try:
        chk=guest(["ha","core","check"],300)
        print("JNS_DOORBELL_MONITOR_HA_CHECK exit="+str(chk.get("exitcode")),flush=True)
        if chk.get("out-data"): print((chk.get("out-data") or "")[-1500:],flush=True)
        if chk.get("exitcode")!=0: raise RuntimeError("HA config check failed")
    except BaseException:
        rr=py(RESTORE,[TARGET,rec["backup"],rec["after_sha256"]])
        print((rr.get("out-data") or "")[-600:],flush=True)
        raise
    before=guest(["docker","inspect","--format","{{.State.StartedAt}}","homeassistant"],30).get("out-data","").strip()
    rr=guest(["ha","core","restart"],300)
    if rr.get("exitcode")!=0: raise RuntimeError("Core restart failed")
    ok=False
    for _ in range(50):
        time.sleep(3)
        try:
            st=(guest(["docker","inspect","--format","{{.State.Running}} {{.State.StartedAt}}","homeassistant"],30).get("out-data") or "").strip()
            if st.startswith("true ") and before not in st: ok=True; break
        except Exception: pass
    if not ok: raise RuntimeError("Core restart not confirmed")
    print("JNS_DOORBELL_MONITOR_DEPLOYED_OK",flush=True)

if __name__=="__main__":
    try:main()
    except Exception as e:
        print("JNS_DOORBELL_MONITOR_BLOCKED "+type(e).__name__+": "+str(e)[:500],flush=True)
        raise SystemExit(2)
