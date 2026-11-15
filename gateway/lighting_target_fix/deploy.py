#!/usr/bin/env python3
import base64,json,pathlib,re,sys,time
sys.path.insert(0,"gateway/arrival_lighting")
from readiness_probe import ssh_host
PATCH=pathlib.Path("gateway/lighting_target_fix/patch.py").read_bytes()

def guest(args,timeout=300):
    d=json.loads(ssh_host("nodeb",["qm","guest","exec","905","--",*args]))
    pid=d.get("pid")
    if not d.get("exited") and not isinstance(pid,int):raise RuntimeError("QGA returned no PID")
    until=time.monotonic()+timeout
    while not d.get("exited"):
        if time.monotonic()>until:raise RuntimeError("QGA timeout pid="+str(pid))
        time.sleep(2)
        d=json.loads(ssh_host("nodeb",["qm","guest","exec-status","905",str(pid)]))
    return d

def run(flag):
    code="exec(compile(__import__('base64').b64decode("+repr(base64.b64encode(PATCH).decode())+"),'<jns-dining-lux>','exec'))"
    r=guest(["docker","exec","homeassistant","python3","-c",code,flag],180)
    out=r.get("out-data") or "";print(out[-5000:],flush=True)
    if r.get("exitcode")!=0:raise RuntimeError((r.get("err-data") or "")[-800:])
    mark="JNS_DINING_LUX_APPLIED" if flag=="--apply" else "JNS_DINING_LUX_PLAN"
    m=re.search(r"(?m)^"+mark+r" (\{[^\n]+\})",out)
    if not m:raise RuntimeError("missing "+mark)
    return json.loads(m.group(1))

def main():
    print("JNS_DINING_LUX_DEPLOY_BEGIN",flush=True)
    if "running" not in ssh_host("nodeb",["qm","status","905"]):raise RuntimeError("VM905 not running")
    # Validate dining light exists and legacy sofa remains disabled.
    check=r'''
from pathlib import Path
import json
ents=json.loads((Path("/config/.storage/core.entity_registry")).read_text())["data"]["entities"]
by={e.get("entity_id"):e for e in ents}
d=by.get("light.livingroom_pendant")
assert d and d.get("disabled_by") is None,"Dining candidate unavailable/disabled"
old=by.get("light.snug_sofa_led")
assert old and old.get("disabled_by") is not None,"legacy Sofa LED unexpectedly active; refuse ambiguous migration"
print("JNS_DINING_ENTITY_PREFLIGHT_OK")
'''
    enc=base64.b64encode(check.encode()).decode()
    r=guest(["docker","exec","homeassistant","python3","-c","exec(__import__('base64').b64decode("+repr(enc)+"))"],60)
    if r.get("exitcode")!=0:raise RuntimeError("entity preflight failed "+(r.get("err-data") or "")[-500:])
    run("--dry-run");run("--apply")
    chk=guest(["ha","core","check"],320)
    print("JNS_DINING_LUX_HA_CHECK exit="+str(chk.get("exitcode")),flush=True)
    if chk.get("exitcode")!=0:raise RuntimeError("HA config check failed; backup retained for manual restore")
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
    print("JNS_DINING_LUX_DEPLOYED_OK",flush=True)

if __name__=="__main__":
    try:main()
    except Exception as e:
        print("JNS_DINING_LUX_DEPLOY_BLOCKED "+type(e).__name__+": "+str(e)[:500],flush=True)
        raise SystemExit(2)
