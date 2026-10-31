#!/usr/bin/env python3
import base64,json,pathlib,re,sys,time
sys.path.insert(0,"gateway/arrival_lighting")
from readiness_probe import ssh_host
PATCH=pathlib.Path("gateway/lux_repair/patch.py").read_bytes()

def guest(args,timeout=300):
    d=json.loads(ssh_host("nodeb",["qm","guest","exec","905","--",*args]))
    pid=d.get("pid")
    if not d.get("exited") and not isinstance(pid,int): raise RuntimeError("QGA returned no PID")
    until=time.monotonic()+timeout
    while not d.get("exited"):
        if time.monotonic()>until: raise RuntimeError("QGA timeout pid="+str(pid))
        time.sleep(2)
        d=json.loads(ssh_host("nodeb",["qm","guest","exec-status","905",str(pid)]))
    return d

def run(flag):
    code="exec(compile(__import__('base64').b64decode("+repr(base64.b64encode(PATCH).decode())+"),'<jns-lux-repair>','exec'))"
    r=guest(["docker","exec","homeassistant","python3","-c",code,flag],180)
    out=r.get("out-data") or ""; print(out[-7000:],flush=True)
    if r.get("exitcode")!=0: raise RuntimeError((r.get("err-data") or "")[-900:])
    mark="JNS_LUX_REPAIR_APPLIED" if flag=="--apply" else "JNS_LUX_REPAIR_PLAN"
    m=re.search(r"(?m)^"+mark+r" (\{[^\n]+\})",out)
    if not m: raise RuntimeError("missing "+mark)
    return json.loads(m.group(1))

def restore(rec):
    src=r'''
from pathlib import Path
import hashlib,shutil,sys
root=Path("/config"); bk=Path(sys.argv[1])
expected=__import__("json").loads(sys.argv[2])
paths=[root/"automations.yaml",root/"packages/jns_synthetic_lux_calibration.yaml",root/"packages/outdoor_environment.yaml"]
for p in paths:
    exp=expected[str(p)]["after"]
    assert hashlib.sha256(p.read_bytes()).hexdigest()==exp,"concurrent change "+str(p)
for p in paths: shutil.copy2(bk/p.name,p)
print("JNS_LUX_REPAIR_ROLLBACK_OK")
'''
    code="exec(compile("+repr(src)+",'<restore>','exec'))"
    r=guest(["docker","exec","homeassistant","python3","-c",code,rec["backup"],json.dumps(rec["files"])],120)
    print((r.get("out-data") or "")[-600:],flush=True)
    if r.get("exitcode")!=0: raise RuntimeError("rollback failed")

def postcheck():
    src=r'''
from pathlib import Path
import json,yaml
P=Path("/config")
a=yaml.safe_load((P/"automations.yaml").read_text())
c=next(x for x in a if str(x.get("id"))=="1791918795028")
blob=json.dumps(c,default=str)
checks={
 "controller_tag":"JNS_LUX_WEATHER_DUSK_REPAIR_V2" in str(c.get("description","")),
 "priority_tag":"JNS_LUX_PRIORITY_LADDER_V1" in str(c.get("description","")),
 "met_weather":"weather.forecast_home" in blob,
 "open_meteo_weather":"weather.ha_general" in blob,
 "five_minute_freshness":"<= 300" in blob,
 "dusk_lock":"dusk_lock" in blob,
 "stale_blocks_off":"sensor_fresh" in blob and "safe_off" in blob,
}
env=yaml.safe_load((P/"packages/outdoor_environment.yaml").read_text())
syn=yaml.safe_load((P/"packages/jns_synthetic_lux_calibration.yaml").read_text())
s=json.dumps(syn,default=str); e=json.dumps(env,default=str)
checks["rain_weather_fallback"]="weather.forecast_home" in e and "weather.ha_general" in e
checks["synthetic_consensus"]="weather.forecast_home" in s and "weather.ha_general" in s
assert all(checks.values()),checks
print("JNS_LUX_REPAIR_POSTCHECK_OK "+json.dumps(checks,sort_keys=True))
'''
    enc=base64.b64encode(src.encode()).decode()
    r=guest(["docker","exec","homeassistant","python3","-c","exec(__import__('base64').b64decode("+repr(enc)+"))"],80)
    print((r.get("out-data") or "")[-1500:],flush=True)
    if r.get("exitcode")!=0: raise RuntimeError("postcheck failed "+(r.get("err-data") or "")[-500:])

def main():
    print("JNS_LUX_REPAIR_DEPLOY_BEGIN",flush=True)
    if "running" not in ssh_host("nodeb",["qm","status","905"]): raise RuntimeError("VM905 not running")
    run("--dry-run")
    rec=run("--apply")
    try:
        chk=guest(["ha","core","check"],320)
        print("JNS_LUX_REPAIR_HA_CHECK exit="+str(chk.get("exitcode")),flush=True)
        if chk.get("out-data"):print((chk.get("out-data") or "")[-2200:],flush=True)
        if chk.get("exitcode")!=0:raise RuntimeError("HA config check failed")
    except BaseException:
        restore(rec);raise
    before=(guest(["docker","inspect","--format","{{.State.StartedAt}}","homeassistant"],30).get("out-data") or "").strip()
    rr=guest(["ha","core","restart"],300)
    if rr.get("exitcode")!=0:raise RuntimeError("Core restart command failed")
    ok=False
    for _ in range(55):
        time.sleep(3)
        try:
            st=(guest(["docker","inspect","--format","{{.State.Running}} {{.State.StartedAt}}","homeassistant"],30).get("out-data") or "").strip()
            if st.startswith("true ") and before not in st:ok=True;break
        except Exception:pass
    if not ok:raise RuntimeError("Core restart not confirmed")
    postcheck()
    print("JNS_LUX_REPAIR_DEPLOYED_OK",flush=True)

if __name__=="__main__":
    try:main()
    except Exception as e:
        print("JNS_LUX_REPAIR_DEPLOY_BLOCKED "+type(e).__name__+": "+str(e)[:500],flush=True)
        raise SystemExit(2)
