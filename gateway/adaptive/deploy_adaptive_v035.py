#!/usr/bin/env python3
"""Guarded HA-General Adaptive Intelligence v0.3.5 deploy, no actuator writes."""
import json,shlex,subprocess,time,sys
HOST=["ssh","-T","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes",
      "-o","HostKeyAlias=nodeb.home.arpa","-o","ConnectTimeout=8",
      "root@10.10.110.12"]
ROOT="/mnt/data/supervisor/homeassistant"
COMP=ROOT+"/custom_components/adaptive_intelligence"
BACK=ROOT+"/.adaptive_intelligence_backups"
STAGE=BACK+"/v035_stage"
SAVE=BACK+"/v034_before_retention_20261117"
HISTORY=ROOT+"/.storage/adaptive_intelligence.history"
DASH=ROOT+"/dashboards/ai-diagnostics.yaml"
STATUS="/tmp/jns_adaptive_v035_config_check.exit"
LOG="/tmp/jns_adaptive_v035_config_check.log"

def command(args,timeout=50):
    q=["qm","guest","exec","905","--"]+args
    p=subprocess.run(HOST+[shlex.join(q)],capture_output=True,text=True,timeout=timeout)
    if p.returncode:raise RuntimeError("Node B transport unavailable: "+p.stderr[-260:])
    try:r=json.loads(p.stdout)
    except Exception as exc:raise RuntimeError("Guest-agent JSON missing") from exc
    if not r.get("exited"):
        pid=r.get("pid")
        if not isinstance(pid,int):raise RuntimeError("Guest-agent process lacks PID")
        for _ in range(40):
            time.sleep(2)
            x=subprocess.run(HOST+[shlex.join(["qm","guest","exec-status","905",str(pid)])],
                             capture_output=True,text=True,timeout=16)
            if x.returncode:raise RuntimeError("Guest process polling unavailable")
            r=json.loads(x.stdout)
            if r.get("exited"):break
    if not r.get("exited"):raise RuntimeError("Guest command remains running")
    if r.get("exitcode")!=0:raise RuntimeError("Guest action failed: "+str(r.get("err-data",""))[-320:])
    return r.get("out-data","")

def sh(src,timeout=50):
    return command(["/bin/sh","-c",src],timeout=timeout)

def main():
    version=command(["/bin/cat",COMP+"/manifest.json"])
    if '"version": "0.3.4"' not in version:
        raise RuntimeError("Live version changed, refusing unreviewed replacement")
    if sh("test ! -e "+shlex.quote(SAVE)+" && echo AVAILABLE").strip()!="AVAILABLE":
        raise RuntimeError("Existing v0.3.4 backup, refusing overwrite")
    print("VERSION_034_VERIFIED",flush=True)
    files=["__init__.py","sensor.py","manifest.json",
           "observation_store.py","zigbee_actions.py"]
    base="https://raw.githubusercontent.com/jamienewton2269/adaptive-intelligence/main/"
    sh("mkdir -p "+shlex.quote(STAGE)+" && mkdir -p "+shlex.quote(SAVE))
    for file in files:
        url=base+"custom_components/adaptive_intelligence/"+file
        sh("curl -fsSL --retry 2 --connect-timeout 8 "+shlex.quote(url)+
           " -o "+shlex.quote(STAGE+"/"+file))
        if sh("test -s "+shlex.quote(STAGE+"/"+file)+" && echo OK").strip()!="OK":
            raise RuntimeError("Incomplete staged file "+file)
    sh("curl -fsSL --retry 2 --connect-timeout 8 "+
       shlex.quote(base+"dashboard/ai-diagnostics.yaml")+" -o "+
       shlex.quote(STAGE+"/ai-diagnostics.yaml"))
    if '"version": "0.3.5"' not in command(["/bin/cat",STAGE+"/manifest.json"]):
        raise RuntimeError("Unverified version in staged files")
    print("STAGE_COMPLETE",flush=True)
    sh("cp -a "+shlex.quote(COMP)+" "+shlex.quote(SAVE+"/integration")+
       " && cp -p "+shlex.quote(DASH)+" "+shlex.quote(SAVE+"/ai-diagnostics.yaml")+
       " && if test -f "+shlex.quote(HISTORY)+
       "; then cp -p "+shlex.quote(HISTORY)+" "+shlex.quote(SAVE+"/history.pre-compaction")+"; fi")
    print("BACKUP_COMPLETE including pre-compaction history",flush=True)

    def rollback():
        sh("cp -a "+shlex.quote(SAVE+"/integration/.")+" "+shlex.quote(COMP)+
           " && rm -f "+shlex.quote(COMP+"/observation_store.py")+" "+
           shlex.quote(COMP+"/zigbee_actions.py")+
           " && cp -p "+shlex.quote(SAVE+"/ai-diagnostics.yaml")+" "+shlex.quote(DASH))
        print("ROLLED_BACK_INTEGRATION_AND_DASHBOARD",flush=True)

    try:
        for file in files:
            sh("cp -p "+shlex.quote(STAGE+"/"+file)+" "+shlex.quote(COMP+"/"+file))
        sh("cp -p "+shlex.quote(STAGE+"/ai-diagnostics.yaml")+" "+shlex.quote(DASH))
        print("V035_STAGED_IN_ACTIVE_PATH; FULL_CONFIG_CHECK_START",flush=True)
        sh("rm -f "+shlex.quote(STATUS)+" "+shlex.quote(LOG)+
           "; (ha core check > "+shlex.quote(LOG)+
           " 2>&1; echo $? > "+shlex.quote(STATUS)+
           ") </dev/null >/dev/null 2>&1 &")
        code="PENDING"
        for _ in range(70):
            code=sh("if test -f "+shlex.quote(STATUS)+"; then cat "+
                    shlex.quote(STATUS)+"; else echo PENDING; fi").strip()
            if code!="PENDING":break
            time.sleep(3)
        if code!="0":
            raise RuntimeError("HA config check failed/incomplete: "+str(code))
    except Exception:
        rollback()
        raise
    print("HA_CORE_CHECK_SUCCESS",flush=True)
    print("V035_DEPLOYED_READY_FOR_CORE_RESTART",flush=True)
    print("NO_LIGHT_OR_HEATING_AUTOMATIONS_CHANGED",flush=True)

if __name__=="__main__":
    try:main()
    except Exception as exc:
        print("DEPLOY_FAILED",type(exc).__name__,str(exc)[-340:],flush=True)
        sys.exit(1)
