#!/usr/bin/env python3
"""JNS Steward-backed VM905 Lux Manual OFF V2 transaction.
The administrator credential stays inside VM905 and is never sent through SSH or QGA.
Only the allowlisted Steward automation.reload capability can use that credential.
"""
import base64
import json
from pathlib import Path
import re
import subprocess
import sys
import time
sys.path.insert(0, "gateway/arrival_lighting")
from readiness_probe import ssh_host

DIR=Path("gateway/lux_manual_override")
CAP="/config/.jns-steward/ha_reload_capability.py"
AUTO="/config/automations.yaml"
PKG="/config/packages/jns_lux_manual_off_v1.yaml"
def qga(args, timeout=240):
    initial=json.loads(ssh_host("nodeb",["qm","guest","exec","905","--",*args]))
    pid=initial.get("pid")
    deadline=time.monotonic()+timeout
    result=initial
    while not result.get("exited"):
        if not isinstance(pid,int):
            raise RuntimeError("QGA operation has no PID: unsafe to retry")
        if time.monotonic()>deadline:
            raise RuntimeError(f"QGA PID {pid} incomplete; no blind retry")
        time.sleep(2)
        result=json.loads(ssh_host("nodeb",["qm","guest","exec-status","905",str(pid)]))
    return result
def cap(mode,auto=None,pkg=None):
    assert mode in ("status","probe","reload")
    argv=["docker","exec","homeassistant","python3",CAP,mode]
    if mode=="reload":
        if not auto or not pkg:raise ValueError("reload requires both verified SHA-256 hashes")
        argv += ["--automations-sha",auto,"--package-sha",pkg]
    result=qga(argv,100)
    output=(result.get("out-data") or "")[-950:]
    error=(result.get("err-data") or "")[-250:]
    print("JNS_STEWARD_CAPABILITY "+mode+" "+output+" "+error,flush=True)
    if result.get("exitcode")!=0:
        raise RuntimeError("Steward "+mode+" failed; exit="+str(result.get("exitcode")))
    required={
        "status":"jns.ha_general.automation_reload",
        "probe":"JNS_STEWARD_HA_API_PROBE_OK",
        "reload":"JNS_STEWARD_HA_AUTOMATIONS_RELOADED_AND_VERIFIED",
    }[mode]
    if required not in output:raise RuntimeError("Steward "+mode+" did not attest result")
def runner(flag):
    p=subprocess.run([sys.executable,str(DIR/"runner_v2.py"),flag],
             capture_output=True,text=True,timeout=175)
    print("JNS_STEWARD_LUX_"+flag.replace("-","").upper()+" "+p.stdout[-6000:],flush=True)
    if p.returncode!=0:raise RuntimeError("Lux "+flag+" failed: "+p.stderr[-250:])
    marker="JNS_LUX_V2_APPLIED" if flag=="--apply" else "JNS_LUX_V2_PLAN"
    m=re.search(re.escape(marker)+r" (\{.+\})",p.stdout)
    if not m:raise RuntimeError("missing Lux "+flag+" attestation")
    return json.loads(m.group(1))
def restore(record):
    code=(DIR/"rollback_v2_vm905.py").read_bytes()
    encoded=base64.b64encode(code).decode()
    source="exec(compile(__import__('base64').b64decode("+repr(encoded)+"),'<jns-lux-v2-restore>','exec'))"
    result=qga(["docker","exec","homeassistant","python3","-c",source,record["backup"],
                json.dumps(record["after_hashes"])],120)
    output=(result.get("out-data") or "")[-1600:]
    print("JNS_STEWARD_LUX_RESTORE "+output,flush=True)
    if result.get("exitcode")!=0 or "JNS_LUX_V2_ROLLBACK_COMPLETE" not in output:
        raise RuntimeError("configuration rollback not confirmed")
def main():
    print("JNS_STEWARD_LUX_V2_BEGIN",flush=True)
    cap("status")
    # Fail BEFORE writing any lighting config when token is absent/unauthorised.
    cap("probe")
    plan=runner("--dry-run")
    if plan.get("core_restart_required") is not False:
        raise RuntimeError("dry-run attempted Core restart")
    record=runner("--apply")
    for path in (AUTO,PKG):
        if path not in record["after_hashes"] or path not in record["before_hashes"]:
            raise RuntimeError("missing rollback SHA for "+path)
    try:
        chk=qga(["ha","core","check"],timeout=285)
        print("JNS_STEWARD_LUX_HA_CORE_CHECK "+json.dumps({
            "exitcode":chk.get("exitcode"),"last_output":(chk.get("out-data") or "")[-400:],
        }),flush=True)
        if chk.get("exitcode")!=0:
            raise RuntimeError("Home Assistant Core rejected the configuration")
        cap("reload",record["after_hashes"][AUTO],record["after_hashes"][PKG])
    except BaseException:
        try:
            restore(record)
            cap("reload",record["before_hashes"][AUTO],record["before_hashes"][PKG])
            print("JNS_STEWARD_LUX_ROLLBACK_ACTIVE",flush=True)
        except BaseException as ex:
            print("JNS_STEWARD_LUX_ROLLBACK_NEEDS_REVIEW "+type(ex).__name__,flush=True)
        raise
    print("JNS_STEWARD_LUX_V2_SUCCESS_NO_CORE_RESTART",flush=True)
if __name__=="__main__":
    try:main()
    except Exception as ex:
        print("JNS_STEWARD_LUX_V2_BLOCKED "+type(ex).__name__+": "+str(ex)[:300],flush=True)
        sys.exit(2)
