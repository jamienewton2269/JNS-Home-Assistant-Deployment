#!/usr/bin/env python3
"""Time-bounded, exclusive security-owner failback on the EXISTING Node C runner.

Cron user is Node C's authorised SSH gateway. Never revive VM906 while VM905
could also command its ESPHome outputs. If ESPHome ownership cannot be proven
absent, suspend ONLY VM905 before restoring source. On transport/identity
failure, fail closed and do not start a potentially competing controller.

Requires onsite approval for the temporary maintenance window. Normal
preparation never calls --restore. No live changes with --check.
"""
import datetime
import fcntl
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import time

BASE=Path.home()/".local/share/jns-security-failback-20261028"
STATE=BASE/"state.json"
LOCK=BASE/"lock"
SOURCE=Path(__file__).resolve()
SSH=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=6"]
TAG="JNS_HA906_SAFE_AUTO_FAILBACK"

def note(k,v):print(TAG+"_"+k+"="+str(v),flush=True)
def run(argv,timeout=30):
    try:return subprocess.run(argv,capture_output=True,text=True,timeout=timeout)
    except (OSError,subprocess.TimeoutExpired):return None
def ssh(node,argv,timeout=30):
    return run(SSH+[node,shlex.join(argv)],timeout)
def healthy(r,expected=None):
    return bool(r and r.returncode==0 and (expected is None or expected in r.stdout))
def status(node,vm):
    r=ssh(node,["qm","status",str(vm)],20)
    if not healthy(r):return None
    m=re.fullmatch(r"status: ([a-z]+)\s*",r.stdout)
    return m.group(1) if m else None
def name_is(node,vm,expected):
    r=ssh(node,["qm","config",str(vm)],22)
    return healthy(r) and bool(re.search(r"(?m)^name: "+re.escape(expected)+r"\s*$",r.stdout))
def nodea_done():
    r=ssh("nodea",["sh","-c","test -e /var/lib/jns-solar/consolidation/vm906-handover-complete-20261028"],18)
    return bool(r and r.returncode==0)
def qga(node,vm,argv,timeout=65):
    p=ssh(node,["qm","guest","exec",str(vm),"--",*argv],35)
    if not healthy(p):return None
    try:obj=json.loads(p.stdout)
    except (ValueError,TypeError):return None
    deadline=time.monotonic()+timeout
    while not obj.get("exited") and time.monotonic()<deadline:
        if not obj.get("pid"):return None
        time.sleep(.6)
        p=ssh(node,["qm","guest","exec-status",str(vm),str(obj["pid"])],23)
        if not healthy(p):return None
        try:obj=json.loads(p.stdout)
        except (ValueError,TypeError):return None
    return obj if obj.get("exited") and not obj.get("out-truncated") else None

COUNT_SCRIPT = """import json,pathlib
p=pathlib.Path('/config/.storage/core.config_entries')
if p.is_symlink() or not p.is_file():raise SystemExit(21)
d=json.loads(p.read_text()).get('data',{}).get('entries',[])
if not isinstance(d,list):raise SystemExit(22)
entries=[x for x in d if isinstance(x,dict) and x.get('domain')=='esphome' and not x.get('disabled_by')]
print('JNS_ESPHOME_ACTIVE_COUNT='+str(len(entries)))
"""
def active_target_count():
    r=qga("nodeb",905,["docker","exec","homeassistant","python3","-c",COUNT_SCRIPT],75)
    if not r or r.get("exitcode")!=0:return None
    a=[x.split("=",1)[-1] for x in str(r.get("out-data","")).splitlines()
       if x.startswith("JNS_ESPHOME_ACTIVE_COUNT=")]
    if len(a)!=1 or not a[0].isdigit():return None
    return int(a[0])
def verified_source():
    return name_is("nodea",906,"ha-security")
def verified_target():
    return name_is("nodeb",905,"ha-s2-general")
def check():
    x={"runner":os.uname().nodename.split(".")[0],
       "vm906_source_state":status("nodea",906),
       "vm905_target_state":status("nodeb",905),
       "source_identity":verified_source(),
       "target_identity":verified_target(),
       "current_target_esphome_count":active_target_count(),
       "deadline_armed":STATE.is_file()}
    note("CHECK",json.dumps(x,sort_keys=True))
    return 0 if x["runner"]=="nodec" and x["source_identity"] and x["target_identity"] else 1
def install():
    if os.uname().nodename.split(".")[0]!="nodec":return 1
    if not verified_source() or not verified_target():return 1
    if status("nodea",906)!="running" or status("nodeb",905)!="running":return 1
    if active_target_count()!=0:return 1
    BASE.mkdir(parents=True,exist_ok=True,mode=0o700)
    if BASE.is_symlink():return 1
    target=BASE/"auto_failback.py"
    if target.is_symlink():return 1
    code=SOURCE.read_bytes()
    if target.exists() and target.read_bytes()!=code:return 1
    if not target.exists():
        with target.open("xb") as f:
            f.write(code);f.flush();os.fsync(f.fileno())
    target.chmod(0o700)
    existing=run(["crontab","-l"],12)
    old=existing.stdout if existing and existing.returncode==0 else ""
    marker="# jns-security-exclusive-failback-20261028"
    if marker in old:note("CRON","already_present")
    else:
        entry="* * * * * /usr/bin/python3 "+shlex.quote(str(target))+" --cron "+marker
        p=run(["crontab","-"],18) if False else None
        try:
            new=subprocess.run(["crontab","-"],input=old.rstrip("\n")+"\n"+entry+"\n",
                               text=True,capture_output=True,timeout=20)
        except (OSError,subprocess.TimeoutExpired):return 1
        if new.returncode:return 1
        note("CRON","installed_inert")
    return 0
def arm():
    if check():return 1
    if status("nodea",906)!="running" or status("nodeb",905)!="running" or active_target_count()!=0:return 1
    if STATE.exists() or STATE.is_symlink():return 1
    jobs=run(["crontab","-l"],12)
    if not healthy(jobs,"# jns-security-exclusive-failback-20261028"):return 1
    BASE.mkdir(parents=True,exist_ok=True,mode=0o700)
    deadline=int(time.time())+35*60
    with STATE.open("x") as f:
        json.dump({"source_vm":906,"target_vm":905,"deadline":deadline,
                   "armed_at":int(time.time()),"onsite_approved":True},f)
        f.flush();os.fsync(f.fileno())
    STATE.chmod(0o600)
    note("ARMED","35_minutes_target_fencing_before_nodea_45_minute_guard")
    return 0
def restore():
    if os.uname().nodename.split(".")[0]!="nodec":return 1
    if nodea_done():note("RESULT","already_accepted");return 0
    if not verified_source() or not verified_target():
        note("BLOCKED","identity");return 1
    a=status("nodea",906)
    if a=="running":note("RESULT","source_still_running");return 0
    if a!="stopped":note("BLOCKED","source_unknown");return 1
    b=status("nodeb",905)
    if b is None:note("BLOCKED","target_state_unknown");return 1
    if b=="running":
        count=active_target_count()
        if count is None or count>0:
            # Safety over continuity: only VM905 may be suspended, and ONLY
            # in the actual failure recovery. No other guest is operated upon.
            p=ssh("nodeb",["qm","suspend","905"],130)
            if not healthy(p) or status("nodeb",905)!="suspended":
                note("BLOCKED","target_fence_not_verified");return 1
            note("TARGET_FENCE","vm905_suspended_failback")
        elif count==0:
            note("TARGET_FENCE","vm905_core_live_without_esphome")
        else:return 1
    elif b not in ("stopped","suspended"):
        note("BLOCKED","target_not_isolated");return 1
    # Fencing must remain true at the moment of source promotion.
    b=status("nodeb",905)
    if b=="running" and active_target_count()!=0:
        note("BLOCKED","target_active_after_fence");return 1
    if b not in ("running","stopped","suspended"):
        note("BLOCKED","target_status_unavailable");return 1
    if nodea_done():return 0
    # Authorize the separate Node A 45-minute timer only AFTER Node C
    # independently confirmed no active target ESPHome controller remains.
    attest=r"""import json,os,pathlib,time
p=pathlib.Path("/var/lib/jns-solar/consolidation/vm905-fenced-for-906-recovery-20261028")
if os.geteuid()!=0 or os.uname().nodename.split(".")[0]!="nodea":raise SystemExit(71)
if p.is_symlink():raise SystemExit(72)
if not p.exists():
 with p.open("x") as f:
  json.dump({"safe_recovery_gate":True,"source_vm":906,"target_vm":905,"verified_at":int(time.time())},f)
  f.flush();os.fsync(f.fileno())
 p.chmod(0o600)
print("JNS_NODEA_RECOVERY_ATTESTED=yes")
"""
    proof=ssh("nodea",["python3","-c",attest],35)
    if not healthy(proof,"JNS_NODEA_RECOVERY_ATTESTED=yes"):
        note("BLOCKED","nodea_exclusivity_attestation_failed");return 1
    started=ssh("nodea",["qm","start","906"],110)
    if not healthy(started) and status("nodea",906)!="running":
        note("BLOCKED","vm906_start_failed");return 1
    if status("nodea",906)!="running":
        note("BLOCKED","vm906_not_running");return 1
    note("RESULT","vm906_running_exclusive_restoration")
    return 0
def main():
    if os.uname().nodename.split(".")[0]!="nodec":return 1
    mode=sys.argv[1] if len(sys.argv)==2 else ""
    if mode=="--check":return check()
    if mode=="--install-inert":return install()
    if mode=="--arm":return arm()
    if mode not in ("--cron","--restore"):return 2
    if not STATE.is_file() or STATE.is_symlink():return 0 if mode=="--cron" else 1
    try:
        state=json.loads(STATE.read_text())
        if state.get("source_vm")!=906 or state.get("target_vm")!=905:return 1
        if mode=="--cron" and time.time()<state["deadline"]:return 0
    except (OSError,ValueError,TypeError,KeyError):return 1
    BASE.mkdir(parents=True,exist_ok=True,mode=0o700)
    with LOCK.open("a+") as f:
        try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return 0
        return restore()
if __name__=="__main__":sys.exit(main())
