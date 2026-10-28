#!/usr/bin/env python3
"""Dormant, ROOT-LOCAL ONLY, fixed-purpose JNS heating v0.3.6 release.

Never run from a checkout or GitHub Actions. A separately installed root-owned
copy on Node C requires local, one-use approval and an admin API token resident
ONLY on Node B. Do not attach this to a dispatcher without separate review.
"""
from __future__ import annotations
import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shlex
import stat
import subprocess
import sys
import time
from v036_release_policy import (
    STAGE, VM, HOST, PRE_REQUIRED, CANDIDATE, ORIGINAL,
    Denied, approve, stage as validate_stage, live_heating, live_post,
)

INSTALL=Path("/usr/local/libexec/jns-heating-v036")
APPROVAL=Path("/etc/jns/heating-v036")
LOCK=Path("/run/lock/jns-heating-v036.lock")
COMP="/mnt/data/supervisor/homeassistant/custom_components/jns_heating_zones"
STAGED="/mnt/data/supervisor/homeassistant/.jns_heating_backups/"+STAGE

class Blocked(RuntimeError):
    pass

def require(value,message):
    if not value:raise Blocked(message)

def protected_file(path):
    require(path.is_file() and not path.is_symlink(),"root-owned file absent")
    s=path.stat()
    require(s.st_uid==0 and s.st_mode & 0o077==0,"root-owned file not private")
    return path.read_bytes()

def gate():
    require(os.geteuid()==0,"local root operation mandatory")
    require(Path(__file__).resolve()==INSTALL/"v036_root_operator.py",
            "never execute release from a repository checkout")
    require(INSTALL.is_dir() and not INSTALL.is_symlink(),
            "root-owned installation directory missing")
    root_mode=INSTALL.stat()
    require(root_mode.st_uid==0 and stat.S_IMODE(root_mode.st_mode)==0o700,
            "installed code directory must be root-owned 0700")
    for name in ("v036_root_operator.py","v036_release_policy.py",
                 "bathroom_v036_transaction.py"):
        protected_file(INSTALL/name)
    require(APPROVAL.is_dir() and not APPROVAL.is_symlink(),
            "operator approval directory missing")
    mode=APPROVAL.stat()
    require(mode.st_uid==0 and stat.S_IMODE(mode.st_mode)==0o700,
            "approval directory must be root-owned mode 0700")
    job=json.loads(protected_file(APPROVAL/"job.json"))
    permit=json.loads(protected_file(APPROVAL/"approval.json"))
    approve(job,permit)
    return job

def run(argv,timeout=50):
    try:
        result=subprocess.run(argv,text=True,capture_output=True,timeout=timeout)
    except (OSError,subprocess.TimeoutExpired) as exc:
        raise Blocked("trusted command unavailable") from exc
    require(result.returncode==0,"trusted management command returned error")
    return result.stdout.strip()

def on_nodeb(argv,timeout=45):
    ssh=["/usr/sbin/runuser","-u","github-runner","--","/usr/bin/ssh",
         "-o","BatchMode=yes","-o","StrictHostKeyChecking=yes",
         "-o","ConnectTimeout=6","root@"+HOST]
    require(run(ssh+["hostname -s"],18)=="nodeb","wrong Proxmox host")
    return run(ssh+[shlex.join(argv)],timeout)

def guest(command,timeout=125):
    def request(argv):
        return json.loads(on_nodeb(["qm",*argv],45))
    reply=request(["guest","exec",VM,"--",*command])
    until=time.monotonic()+timeout
    while not reply.get("exited"):
        require(isinstance(reply.get("pid"),int) and time.monotonic()<until,
                "guest-agent operation outcome uncertain")
        time.sleep(2)
        reply=request(["guest","exec-status",VM,str(reply["pid"])])
    require(reply.get("exitcode")==0,"guest-agent operation exited nonzero")
    return (reply.get("out-data") or "").strip()

def guest_python(script,container=True):
    if container:
        args=["docker","exec","homeassistant","python3","-c",script]
    else:
        args=["python3","-c",script]
    return guest(args)

def transaction(action):
    require(action in ("verify","apply","rollback"),"transaction not fixed-purpose")
    blob=protected_file(INSTALL/"bathroom_v036_transaction.py")
    body=(
        "import base64,json\n"
        "ns={'__name__':'_jns_v036_operator'}\n"
        "exec(compile(base64.b64decode("+repr(base64.b64encode(blob).decode())+
        "),'<trusted-v036-transaction>','exec'),ns)\n"
        "data=ns["+repr(action)+"]('/config',"+repr(STAGE)+
        (",approved=True)" if action!="verify" else ")")+"\n"
        "print('JNS_V036 '+json.dumps(data,sort_keys=True))\n"
    )
    encoded="exec(__import__('base64').b64decode("+repr(base64.b64encode(body.encode()).decode())+"))"
    output=guest_python(encoded)
    require(output.startswith("JNS_V036 "),"transaction returned no verified marker")
    return json.loads(output.split(" ",1)[1])

def inspect_stage():
    script="import json,pathlib;print(json.dumps(json.loads((pathlib.Path('/config/.jns_heating_backups')/"+repr(STAGE)+"/'state.json').read_text())))"
    validate_stage(json.loads(guest_python(script)))
    report=transaction("verify")
    require(report.get("state")=="staged" and report.get("active_files_sha256_verified"),
            "source is not safely staged")
    # Prove host-level access to each independently restorable original
    # and all six pinned candidates (works even if Core later fails).
    for folder,pinned in (("original",ORIGINAL),("candidate",CANDIDATE)):
        for name,expected in pinned.items():
            path=STAGED+"/"+folder+"/"+name
            result=guest(["sha256sum",path]).split()
            require(result and result[0]==expected,"HAOS host backup fingerprint changed")
    for name,expected in ORIGINAL.items():
        result=guest(["sha256sum",COMP+"/"+name]).split()
        require(result and result[0]==expected,"active baseline changed")

def authenticated():
    """GET-only, from Node B root; administrator token never reaches Node C."""
    code=(
        "import json,stat,urllib.request\n"
        "from pathlib import Path\n"
        "p=Path('/etc/jns/ha-general-api.token')\n"
        "s=p.lstat()\n"
        "assert stat.S_ISREG(s.st_mode) and s.st_uid==0 and stat.S_IMODE(s.st_mode)==0o600\n"
        "token=p.read_text().strip()\n"
        "assert len(token)>=40 and '\\n' not in token\n"
        "req=urllib.request.Request('http://ha-general.home.arpa:80/api/states',"
        "headers={'Authorization':'Bearer '+token})\n"
        "with urllib.request.urlopen(req,timeout=12) as response:\n"
        " assert response.status==200\n"
        " rows=json.load(response)\n"
        "required=set("+repr(PRE_REQUIRED)+")\n"
        "states={v['entity_id']:v for v in rows if v.get('entity_id') in required}\n"
        "advisory=[v for v in rows if v.get('entity_id','').startswith('sensor.') "
        "and 'Bathroom advisory ' in (v.get('attributes') or {}).get('friendly_name','')]\n"
        "print(json.dumps({'states':states,'advisories':advisory}))\n"
    )
    # The configured admin token is read by root on Node B; HTTP 401 fails.
    return json.loads(on_nodeb(["python3","-c",code],55))

def config_check():
    guest(["ha","core","check"],timeout=240)

def core_stamp():
    return guest(["docker","inspect","--format","{{.State.StartedAt}}","homeassistant"])

def restart_and_verify(previous):
    try:
        guest(["ha","core","restart"],timeout=110)
    except Blocked:
        pass  # HAOS may disconnect during a real restart; never assume success.
    end=time.monotonic()+210
    while time.monotonic()<end:
        try:
            stamp=core_stamp()
            if stamp and stamp!=previous:
                snap=authenticated()
                live_heating(snap["states"],require_idle=False)
                return snap
        except (Blocked,Denied,KeyError,ValueError,OSError):
            pass
        time.sleep(7)
    raise Blocked("fresh Core process and authenticated heating recovery not proven")

def host_restore():
    """HAOS host fallback; safe even if the Home Assistant container is down."""
    # This script takes NO external arguments. It refuses unexpected source
    # fingerprints, protecting concurrent releases and edits.
    parts=["set -eu","D="+shlex.quote(COMP),"S="+shlex.quote(STAGED)]
    for folder,pinned in (("original",ORIGINAL),("candidate",CANDIDATE)):
        for name,expected in pinned.items():
            path="$S/"+folder+"/"+name
            parts.extend(["test ! -L \""+path+"\"",
                "test \"$(sha256sum \""+path+"\" | cut -d ' ' -f1)\" = "+expected])
    for name in CANDIDATE:
        current="$D/"+name
        allowed=[CANDIDATE[name]]
        if name in ORIGINAL:allowed.append(ORIGINAL[name])
        parts.extend(["test ! -L \""+current+"\"",
                      "if test -e \""+current+"\"; then",
                      "  sum=$(sha256sum \""+current+"\" | cut -d ' ' -f1)",
                      "  case \"$sum\" in "+"|".join(allowed)+") ;; *) exit 76;; esac",
                      "fi"])
    for name in ORIGINAL:
        parts.extend(["cp -p \"$S/original/"+name+"\" \"$D/.jns-v036-recover-"+name+"\"",
                      "mv -f \"$D/.jns-v036-recover-"+name+"\" \"$D/"+name+"\""])
    for name in set(CANDIDATE)-set(ORIGINAL):
        parts.append("rm -f \"$D/"+name+"\"")
    for name,expected in ORIGINAL.items():
        parts.append("test \"$(sha256sum \"$D/"+name+"\" | cut -d ' ' -f1)\" = "+expected)
    parts.append("echo JNS_V036_ORIGINAL_FILES_RESTORED")
    require(guest(["/bin/sh","-c","\n".join(parts)],timeout=100)==
            "JNS_V036_ORIGINAL_FILES_RESTORED","host fallback not proved")

def preflight():
    # Root-local read-only acceptance check; never consumes the permit,
    # modifies active modules or restarts Core.
    gate()
    require(on_nodeb(["qm","status",VM])=="status: running",
            "VM905 moved or stopped")
    inspect_stage()
    live_heating(authenticated()["states"])
    config_check()
    print("JNS_HEATING_V036_OPERATOR_PREFLIGHT_SAFE "
          "stage_integrity=true authenticated_live_idle=true "
          "rollback_host_backups=true no_source_changes=true",flush=True)

def activate():
    job=gate()
    # O_NOFOLLOW prevents a symlinked lock path from redirecting root writes.
    fd=os.open(LOCK,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,"a+") as lk:
        lk_stat=os.fstat(lk.fileno())
        require(lk_stat.st_uid==0 and stat.S_IMODE(lk_stat.st_mode)==0o600,
                "root-owned exclusive maintenance lock unavailable")
        fcntl.flock(lk,fcntl.LOCK_EX|fcntl.LOCK_NB)
        require(on_nodeb(["qm","status",VM])=="status: running","VM905 moved or stopped")
        inspect_stage()
        baseline=live_heating(authenticated()["states"])
        config_check()
        # Consume the matching one-use root-local permit immediately before
        # irreversible Core-interruption steps. Never write token/permit to GitHub.
        # Revalidate expiry after all potentially slow read-only checks.
        approve(job,json.loads(protected_file(APPROVAL/"approval.json")))
        (APPROVAL/"approval.json").unlink()
        changed=False
        try:
            changed=True
            status=transaction("apply")
            require(status.get("state")=="applied_pending_core_restart",
                    "six-file apply not confirmed")
            config_check()
            live_heating(authenticated()["states"])  # heating still idle
            stamp=core_stamp()
            post=restart_and_verify(stamp)
            live_post(baseline,post["states"],post["advisories"])
            verified=transaction("verify")
            require(verified.get("state")=="applied_pending_core_restart" and
                    verified.get("active_files_sha256_verified"),
                    "post-restart active v0.3.6 source integrity not proved")
            print("JNS_HEATING_V036_LIVE_VERIFIED "+
                  json.dumps({"stage":STAGE,"advisory_entities":3,
                              "thermostat_target_unchanged":True,
                              "numeric_forecast_not_guaranteed":True}),flush=True)
        except BaseException:
            if changed:
                try:
                    try: transaction("rollback")
                    except BaseException:host_restore()
                    stamp=core_stamp()
                    recovered=restart_and_verify(stamp)
                    live_heating(recovered["states"],require_idle=False)
                    print("JNS_HEATING_V034_ROLLBACK_RECOVERED "
                          "stage_state_may_need_reconciliation",flush=True)
                except BaseException:
                    print("JNS_HEATING_CRITICAL_RECOVERY_UNPROVEN",file=sys.stderr,flush=True)
            raise

if __name__=="__main__":
    try:
        require(sys.argv in ([sys.argv[0],"--activate"],[sys.argv[0],"--preflight"]),
                "fixed --preflight or --activate only")
        if sys.argv[1]=="--preflight":preflight()
        else:activate()
    except (Blocked,Denied,ValueError,KeyError,TypeError,OSError,
            subprocess.SubprocessError) as err:
        print("JNS_HEATING_V036_ROOT_BLOCKED",type(err).__name__,str(err)[:140],
              file=sys.stderr)
        raise SystemExit(2)
