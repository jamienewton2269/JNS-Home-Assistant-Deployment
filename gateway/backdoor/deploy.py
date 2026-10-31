#!/usr/bin/env python3
import base64,json,pathlib,re,sys,time
sys.path.insert(0,"gateway/arrival_lighting")
from readiness_probe import ssh_host
PATCH=pathlib.Path("gateway/backdoor/patch_zigbee_v2.py").read_bytes()

def guest(args,timeout=300):
    d=json.loads(ssh_host("nodeb",["qm","guest","exec","905","--",*args]))
    pid=d.get("pid")
    if not d.get("exited") and not isinstance(pid,int): raise RuntimeError("QGA returned no PID")
    deadline=time.monotonic()+timeout
    while not d.get("exited"):
        if time.monotonic()>deadline: raise RuntimeError("QGA timeout pid="+str(pid))
        time.sleep(2)
        d=json.loads(ssh_host("nodeb",["qm","guest","exec-status","905",str(pid)]))
    return d

def run(flag):
    code="exec(compile(__import__('base64').b64decode("+repr(base64.b64encode(PATCH).decode())+"),'<jns-backdoor-zigbee>','exec'))"
    r=guest(["docker","exec","homeassistant","python3","-c",code,flag],150)
    print((r.get("out-data") or "")[-5000:],flush=True)
    if r.get("exitcode")!=0: raise RuntimeError((r.get("err-data") or "")[-800:])
    mark="JNS_BACKDOOR_ZIGBEE_APPLIED" if flag=="--apply" else "JNS_BACKDOOR_ZIGBEE_PLAN"
    m=re.search(r"(?m)^"+mark+r" (\{[^\n]+\})",(r.get("out-data") or ""))
    if not m: raise RuntimeError("missing "+mark)
    return json.loads(m.group(1))

def restore(rec):
    src=r'''
from pathlib import Path
import hashlib,os,shutil,sys
p=Path("/config/packages/jns_garden_features_backdoor.yaml")
bk=Path(sys.argv[1])/"jns_garden_features_backdoor.yaml"
expected=sys.argv[2]
assert hashlib.sha256(p.read_bytes()).hexdigest()==expected,"concurrent package change"
shutil.copy2(bk,p)
print("JNS_BACKDOOR_ZIGBEE_ROLLBACK_OK")
'''
    code="exec(compile("+repr(src)+",'<restore>','exec'))"
    r=guest(["docker","exec","homeassistant","python3","-c",code,rec["backup"],rec["after_sha256"]],120)
    print((r.get("out-data") or "")[-500:],flush=True)
    if r.get("exitcode")!=0: raise RuntimeError("rollback failed")

def main():
    print("JNS_BACKDOOR_ZIGBEE_DEPLOY_BEGIN",flush=True)
    if "running" not in ssh_host("nodeb",["qm","status","905"]): raise RuntimeError("VM905 not running")
    # Confirm new Zigbee entity is live before touching package.
    check=r'''
from pathlib import Path
import json
ents=json.loads((Path("/config/.storage/core.entity_registry")).read_text())["data"]["entities"]
e=next((x for x in ents if x.get("entity_id")=="binary_sensor.backdoor_contact_switch_contact"),None)
assert e and e.get("disabled_by") is None and e.get("platform")=="mqtt"
print("JNS_BACKDOOR_NEW_ENTITY_OK")
'''
    enc=base64.b64encode(check.encode()).decode()
    r=guest(["docker","exec","homeassistant","python3","-c","exec(__import__('base64').b64decode("+repr(enc)+"))"],60)
    if r.get("exitcode")!=0: raise RuntimeError("new Zigbee contact unavailable")
    run("--dry-run")
    rec=run("--apply")
    try:
        chk=guest(["ha","core","check"],300)
        print("JNS_BACKDOOR_ZIGBEE_HA_CHECK exit="+str(chk.get("exitcode")),flush=True)
        if chk.get("out-data"): print((chk.get("out-data") or "")[-1800:],flush=True)
        if chk.get("exitcode")!=0: raise RuntimeError("HA config check failed")
    except BaseException:
        restore(rec); raise

    # Package changed: deterministic guarded Core restart.
    before=(guest(["docker","inspect","--format","{{.State.StartedAt}}","homeassistant"],30).get("out-data") or "").strip()
    rr=guest(["ha","core","restart"],300)
    if rr.get("exitcode")!=0: raise RuntimeError("Core restart command failed")
    ok=False
    for _ in range(50):
        time.sleep(3)
        try:
            st=(guest(["docker","inspect","--format","{{.State.Running}} {{.State.StartedAt}}","homeassistant"],30).get("out-data") or "").strip()
            if st.startswith("true ") and before not in st: ok=True; break
        except Exception: pass
    if not ok: raise RuntimeError("Core restart not confirmed")
    print("JNS_BACKDOOR_ZIGBEE_DEPLOYED_OK",flush=True)
    print("trigger=binary_sensor.backdoor_contact_switch_contact",flush=True)
    print("timer=timer.jns_backdoor_dogs_run",flush=True)
    print("duration=input_number.jns_backdoor_dogs_run_minutes",flush=True)
    print("rule=ignore-open-while-timer-active",flush=True)

if __name__=="__main__":
    try: main()
    except Exception as e:
        print("JNS_BACKDOOR_ZIGBEE_BLOCKED "+type(e).__name__+": "+str(e)[:500],flush=True)
        raise SystemExit(2)
