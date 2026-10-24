#!/usr/bin/env python3
"""DORMANT JNS root-owned VM905 heating v0.3.5 promotion handler.

NOT installed, NOT enabled, NOT callable by the current Node C gateway.
Once independently reviewed, only the trusted root-owned JNS dispatcher may
invoke this fixed handler for one allowlisted JSON job type. A separately
root-created 15-minute permit is mandatory; GitHub alone cannot activate.

Only HA-General VM905. Root-owned installed files MUST be under
/usr/local/libexec/jns-heating-v035/ and remain non-writable to runner.
"""
from __future__ import annotations
import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import time

from promotion_policy import (
    approve, PolicyDenied, STAGE_ID, CANDIDATE_SHA, BASELINE_SHA,
)

INSTALL=Path("/usr/local/libexec/jns-heating-v035")
APPROVAL=Path("/etc/jns/heating-v035/approval.json")
LOCK=Path("/run/lock/jns-heating-v035-promotion.lock")
HOST_ROOT="/mnt/data/supervisor/homeassistant"
STAGE=f"{HOST_ROOT}/.jns_heating_backups/{STAGE_ID}"
LIVE=f"{HOST_ROOT}/custom_components/jns_heating_zones"
VM="905"
NODE="nodeb.home.arpa"


class DeploymentBlocked(RuntimeError):
    pass


def guard_filesystem():
    if os.geteuid()!=0:
        raise DeploymentBlocked("root-owned execution required")
    for path in (INSTALL, Path(__file__).resolve(), INSTALL/"transaction.py",
                 INSTALL/"promotion_policy.py"):
        st=path.lstat()
        if path.is_symlink() or st.st_uid!=0 or st.st_mode & 0o022:
            raise DeploymentBlocked("non-root or writeable privileged code")
    if not str(Path(__file__).resolve()).startswith(str(INSTALL)+"/"):
        raise DeploymentBlocked("root handler invoked outside immutable installation")


def read_permit():
    parent=APPROVAL.parent
    for path in (parent,APPROVAL):
        if path.is_symlink() or not path.exists():
            raise DeploymentBlocked("locally approved heating permit missing")
        st=path.stat()
        if st.st_uid!=0 or st.st_mode & 0o077:
            raise DeploymentBlocked("permit is not root-private")
    return json.loads(APPROVAL.read_text())


def run(command, timeout):
    proc=subprocess.run(command,capture_output=True,text=True,timeout=timeout)
    if proc.returncode!=0:
        raise DeploymentBlocked("trusted management command failed")
    return proc.stdout.strip()


def host_command(argv, timeout=35):
    opts=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes",
          "-o","ConnectTimeout=6","root@"+NODE]
    if run(opts+["hostname -s"],15)!="nodeb":
        raise DeploymentBlocked("wrong physical Proxmox host")
    return run(opts+[shlex.join(argv)],timeout)


def guest(argv, timeout=80):
    response=json.loads(host_command(["qm","guest","exec",VM,"--",*argv],timeout=35))
    deadline=time.monotonic()+timeout
    while not response.get("exited"):
        pid=response.get("pid")
        if not isinstance(pid,int) or time.monotonic()>deadline:
            raise DeploymentBlocked("VM905 command status unknown; manual review")
        time.sleep(2)
        response=json.loads(host_command(["qm","guest","exec-status",VM,str(pid)],35))
    if response.get("exitcode")!=0:
        raise DeploymentBlocked("VM905 command returned failure")
    return (response.get("out-data") or "").strip()


def run_transaction(action,approved=False):
    if action not in ("verify","commit","rollback"):
        raise DeploymentBlocked("invalid transaction action")
    code=(INSTALL/"transaction.py").read_bytes()
    args=["transaction.py",action,"--root","/config","--stage-id",STAGE_ID]
    if approved:
        args+=["--gateway-authorised"]
    statement=(
        "import base64,sys\n"
        "sys.argv="+repr(args)+"\n"
        "exec(compile(base64.b64decode("+repr(base64.b64encode(code).decode())+
        "),'<jns-root-approved-heating-transaction>','exec'))\n"
    )
    cmd="exec(__import__('base64').b64decode('"+base64.b64encode(statement.encode()).decode()+"'))"
    output=guest(["docker","exec","homeassistant","python3","-c",cmd],timeout=95)
    marker="JNS_HEATING_GUARDED "
    if not output.startswith(marker):
        raise DeploymentBlocked("unexpected heating transaction response")
    return json.loads(output[len(marker):])


def config_check():
    # A read-only Supervisor configuration check, never a thermostat command.
    guest(["ha","core","check"],timeout=220)


def core_ready():
    # Inside-container loopback only, no token, no confidential response body.
    expr=(
        "import urllib.request,urllib.error\n"
        "try:\n"
        " r=urllib.request.urlopen('http://127.0.0.1:8123/api/',timeout=6)\n"
        " print('READY' if r.status in (200,401) else 'WAIT')\n"
        "except urllib.error.HTTPError as e:\n"
        " print('READY' if e.code==401 else 'WAIT')\n"
        "except Exception:\n"
        " print('WAIT')\n"
    )
    try:
        return guest(["docker","exec","homeassistant","python3","-c",expr],timeout=30).strip()=="READY"
    except (DeploymentBlocked,subprocess.TimeoutExpired):
        return False


def await_core(seconds=170):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        if core_ready():
            return True
        time.sleep(8)
    return False


def digest_on_host(path):
    if not path.startswith(HOST_ROOT+"/") or "'" in path or "\n" in path:
        raise DeploymentBlocked("host path outside VM905 Home Assistant")
    content=guest(["sha256sum",path],timeout=35)
    fields=content.split()
    if not fields or not re.fullmatch(r"[a-f0-9]{64}",fields[0]):
        raise DeploymentBlocked("HAOS host path not verifiable")
    return fields[0]


def verify_host_recovery():
    old=f"{STAGE}/original/thermal.py"
    current=f"{LIVE}/thermal.py"
    candidate=f"{STAGE}/candidate.py"
    if (digest_on_host(old)!=BASELINE_SHA
            or digest_on_host(current)!=BASELINE_SHA
            or digest_on_host(candidate)!=CANDIDATE_SHA):
        raise DeploymentBlocked("HAOS host rollback prerequisites changed")


def host_fallback_rollback(new_manifest_sha,old_manifest_sha):
    # Recovery operates in HAOS host filesystem: Core may not start.
    for value in (new_manifest_sha,old_manifest_sha):
        if not re.fullmatch(r"[0-9a-f]{64}",value):
            raise DeploymentBlocked("missing pinned manifest digest for emergency fallback")
    # Every path and digest is fixed or strictly validated. No job input is
    # interpolated into shell. The original learning store is NEVER restored
    # over current observations.
    sh_script=f"""set -eu
D='{LIVE}'
B='{STAGE}/original'
OLD='{BASELINE_SHA}'
NEW='{CANDIDATE_SHA}'
OLDM='{old_manifest_sha}'
NEWM='{new_manifest_sha}'
test "$(sha256sum "$B/thermal.py" | cut -d' ' -f1)" = "$OLD"
test "$(sha256sum "$B/manifest.json" | cut -d' ' -f1)" = "$OLDM"
test "$(sha256sum "$D/thermal.py" | cut -d' ' -f1)" = "$NEW"
test "$(sha256sum "$D/manifest.json" | cut -d' ' -f1)" = "$NEWM"
test ! -L "$D/thermal.py"
test ! -L "$D/manifest.json"
cp -p "$B/thermal.py" "$D/.jns-heating-emergency-thermal"
cp -p "$B/manifest.json" "$D/.jns-heating-emergency-manifest"
mv -f "$D/.jns-heating-emergency-thermal" "$D/thermal.py"
mv -f "$D/.jns-heating-emergency-manifest" "$D/manifest.json"
test "$(sha256sum "$D/thermal.py" | cut -d' ' -f1)" = "$OLD"
test "$(sha256sum "$D/manifest.json" | cut -d' ' -f1)" = "$OLDM"
echo JNS_RECOVERY_ORIGINALS_RESTORED
"""
    report=guest(["/bin/sh","-c",sh_script],timeout=65)
    if "JNS_RECOVERY_ORIGINALS_RESTORED" not in report:
        raise DeploymentBlocked("host-level emergency recovery unverified")


def stage_metadata():
    # Data originates from the private local snapshot; never from queue JSON.
    statement=(
        "import json\n"
        "from pathlib import Path\n"
        "x=json.loads((Path('/config/.jns_heating_backups')/"+repr(STAGE_ID)+
        "/'state.json').read_text())\n"
        "print(json.dumps({k:x[k] for k in ('state','stage_id',"
        "'legacy_manifest_sha','new_manifest_sha','candidate_sha')}))"
    )
    output=guest(["docker","exec","homeassistant","python3","-c",statement],timeout=35)
    result=json.loads(output)
    if result.get("state")!="staged" or result.get("stage_id")!=STAGE_ID or result.get("candidate_sha")!=CANDIDATE_SHA:
        raise DeploymentBlocked("staged snapshot not current")
    return result


def perform(job):
    # The root-owned wrapper is expected to supply a strict allowlisted JSON
    # gateway job; the job alone is not authorization to interrupt heating.
    guard_filesystem()
    permit=read_permit()
    approve(job,permit)
    if "running" not in host_command(["qm","status",VM],timeout=30):
        raise DeploymentBlocked("VM905 not running")
    with LOCK.open("a+") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        # Consume local one-use approval BEFORE beginning any operation.
        APPROVAL.unlink()
        stage=stage_metadata()
        status=run_transaction("verify")
        if status.get("state")!="staged" or status.get("runtime_reload") is not False:
            raise DeploymentBlocked("staged backup not verified")
        verify_host_recovery()
        if not core_ready():
            raise DeploymentBlocked("HA-General Core not answering before update")
        config_check()
        # No Core / thermostat writes before all checks above.
        applied=False
        try:
            outcome=run_transaction("commit",approved=True)
            if outcome.get("state")!="applied_pending_runtime_verification":
                raise DeploymentBlocked("candidate commit not confirmed")
            applied=True
            config_check()
            guest(["ha","core","restart"],timeout=95)
            if not await_core():
                raise DeploymentBlocked("Home Assistant Core health not confirmed after restart")
            if digest_on_host(f"{LIVE}/thermal.py")!=CANDIDATE_SHA:
                raise DeploymentBlocked("deployed thermal version changed")
            print("JNS_HEATING_V035_ACTIVATED",json.dumps({
                "stage_id":STAGE_ID,"runtime_responding":True,
                "manual_control_unchanged":True}),flush=True)
        except BaseException:
            if applied:
                try:
                    # Standard rollback uses the transaction and records state.
                    run_transaction("rollback",approved=True)
                except BaseException:
                    # Independent host file-mount fallback works if Core is down.
                    host_fallback_rollback(stage["new_manifest_sha"],stage["legacy_manifest_sha"])
                # Reload restored original module; do not touch samples.
                try:
                    guest(["ha","core","restart"],timeout=95)
                    if not await_core():
                        raise DeploymentBlocked("Core not confirmed after rollback restart")
                    print("JNS_HEATING_V034_ROLLBACK_RECOVERED",flush=True)
                except BaseException:
                    print("JNS_HEATING_EMERGENCY_INTERVENTION_REQUIRED",flush=True)
            raise


def main():
    if len(sys.argv)!=2 or not Path(sys.argv[1]).is_file():
        raise DeploymentBlocked("one approved gateway job JSON required")
    if not str(Path(sys.argv[1]).resolve()).startswith("/home/github-runner/actions-runner/"):
        # Actual dispatcher must retain its original queue path guard too;
        # this check is intentionally restrictive and must be reviewed on Node C.
        raise DeploymentBlocked("queue path not in recognised JNS runner directory")
    job=json.loads(Path(sys.argv[1]).read_text())
    perform(job)

if __name__=="__main__":
    try:
        main()
    except (PolicyDenied,DeploymentBlocked,OSError,ValueError,KeyError,
            subprocess.TimeoutExpired,subprocess.SubprocessError) as exc:
        print("JNS_HEATING_PROMOTION_BLOCKED",type(exc).__name__,str(exc)[:150],flush=True)
        sys.exit(2)
