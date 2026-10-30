#!/usr/bin/env python3
"""Transactional Node C -> Node B -> HA-General stale/dusk Lux deployment."""
import base64,json,re,sys,time
from pathlib import Path
sys.path.insert(0,"gateway/arrival_lighting")
from readiness_probe import ssh_host

DIR=Path("gateway/lux_stale_dusk")
PATCH=(DIR/"patch_vm905.py").read_bytes()

def guest(args,timeout=300):
    r=json.loads(ssh_host("nodeb",["qm","guest","exec","905","--",*args]))
    deadline=time.monotonic()+timeout
    while not r.get("exited"):
        pid=r.get("pid")
        if not isinstance(pid,int): raise RuntimeError("QGA returned no PID; no blind retry")
        if time.monotonic()>deadline: raise RuntimeError("QGA PID still running: "+str(pid))
        time.sleep(2)
        r=json.loads(ssh_host("nodeb",["qm","guest","exec-status","905",str(pid)]))
    return r

def run_patch(flag):
    code="exec(compile(__import__('base64').b64decode("+repr(base64.b64encode(PATCH).decode())+"),'<jns-lux-stale-dusk>','exec'))"
    r=guest(["docker","exec","homeassistant","python3","-c",code,flag],160)
    out=r.get("out-data") or ""
    print(out[-8000:],flush=True)
    if r.get("exitcode")!=0: raise RuntimeError((r.get("err-data") or "")[-600:])
    marker="JNS_LUX_STALE_DUSK_APPLIED" if flag=="--apply" else "JNS_LUX_STALE_DUSK_PLAN"
    m=re.search(r"(?m)^"+marker+r" (\{[^\n]+\})",out)
    if not m: raise RuntimeError("missing "+marker)
    return json.loads(m.group(1))

def restore(backup,after_sha):
    src=r'''
from pathlib import Path
import hashlib,os,stat,tempfile,sys
A=Path("/config/automations.yaml"); B=Path(sys.argv[1])/"automations.yaml"
expected=sys.argv[2]
assert hashlib.sha256(A.read_bytes()).hexdigest()==expected,"concurrent automations change"
old=B.read_bytes(); st=A.stat()
fd,tmp=tempfile.mkstemp(prefix=".jns-lux-stale-restore-",dir=str(A.parent))
try:
  with os.fdopen(fd,"wb") as f:f.write(old);f.flush();os.fsync(f.fileno())
  os.chown(tmp,st.st_uid,st.st_gid);os.chmod(tmp,stat.S_IMODE(st.st_mode));os.replace(tmp,A)
finally:
  if os.path.exists(tmp):os.unlink(tmp)
print("JNS_LUX_STALE_DUSK_ROLLBACK_VERIFIED")
'''
    code="exec(compile("+repr(src)+",'<restore>','exec'))"
    r=guest(["docker","exec","homeassistant","python3","-c",code,backup,after_sha],120)
    if r.get("exitcode")!=0 or "ROLLBACK_VERIFIED" not in (r.get("out-data") or ""):
        raise RuntimeError("rollback verification failed "+(r.get("err-data") or "")[-400:])
    print((r.get("out-data") or "").strip(),flush=True)

def main():
    print("JNS_LUX_STALE_DUSK_DEPLOY_BEGIN",flush=True)
    if "running" not in ssh_host("nodeb",["qm","status","905"]): raise RuntimeError("VM905 not running")
    run_patch("--dry-run")
    rec=run_patch("--apply")
    try:
        chk=guest(["ha","core","check"],320)
        print("JNS_LUX_STALE_DUSK_HA_CHECK exit="+str(chk.get("exitcode")),flush=True)
        if chk.get("out-data"): print((chk.get("out-data") or "")[-2500:],flush=True)
        if chk.get("exitcode")!=0: raise RuntimeError("HA Core config check failed")
    except BaseException:
        restore(rec["backup"],rec["after_sha256"])
        raise

    # Automation-only edit: reload automations rather than restart Core.
    reload_cmd=r'''python3 - <<'PY'
import urllib.request,json,os
# Prefer supervisor-managed local Core API token when available inside the HA container.
token=os.environ.get("SUPERVISOR_TOKEN","")
if not token: raise SystemExit(3)
req=urllib.request.Request("http://supervisor/core/api/services/automation/reload",
    data=b"{}",method="POST",
    headers={"Authorization":"Bearer "+token,"Content-Type":"application/json"})
with urllib.request.urlopen(req,timeout=15) as r: print(r.status)
PY'''
    rr=guest(["docker","exec","homeassistant","sh","-c",reload_cmd],60)
    if rr.get("exitcode")!=0:
        # Native fallback: one guarded Core restart only.
        print("JNS_LUX_STALE_DUSK_RELOAD_UNAVAILABLE; guarded Core restart",flush=True)
        restart=guest(["ha","core","restart"],300)
        if restart.get("exitcode")!=0: raise RuntimeError("Core restart failed")
    print("JNS_LUX_STALE_DUSK_DEPLOY_OK",flush=True)

if __name__=="__main__":
    try: main()
    except Exception as e:
        print("JNS_LUX_STALE_DUSK_DEPLOY_BLOCKED "+type(e).__name__+": "+str(e)[:400],flush=True)
        raise SystemExit(2)
