#!/usr/bin/env python3
"""Start already-restored VM906 on Node A using established Node C GitHub runner.

Fail closed if original VM906 QEMU process or PID is visible on Node C.
Node A VM must be stopped, named ha-security, with onboot 0 and rootfs on vmdata.
Keep Node A onboot=0 until old Node C startup is fenced by Node C root.
Never modify Node C VM, original NFS backup, or other VMs.
"""
import os
import re
import shlex
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

SSH=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes",
     "-o","ConnectTimeout=6","nodea"]

def note(s):
    print("JNS_VM906_"+s,flush=True)

def remote(script,timeout=40):
    try:
        p=subprocess.run(SSH+[shlex.join(["bash","-c",script])],
           capture_output=True,text=True,timeout=timeout)
    except (OSError,subprocess.TimeoutExpired):
        raise RuntimeError("NODEA_CONNECTION_OR_COMMAND_TIMEOUT") from None
    if p.returncode:
        raise RuntimeError("NODEA_COMMAND_FAILED_RC_"+str(p.returncode))
    return p.stdout

def source_proc_running():
    try:
        p=subprocess.run(["ps","-eo","args="],
                capture_output=True,text=True,timeout=12)
    except (OSError,subprocess.TimeoutExpired):
        raise RuntimeError("NODEC_SOURCE_PROCESS_CHECK_UNAVAILABLE") from None
    if p.returncode:
        raise RuntimeError("NODEC_PS_FAILED")
    for l in p.stdout.splitlines():
        if ("qemu-system" in l or "kvm " in l) and re.search(r" -id 906(?:\s|$)",l):
            return True
    return False

def source_fenced():
    if os.uname().nodename.split(".")[0]!="nodec" or os.geteuid()==0:
        raise RuntimeError("EXPECTED_UNPRIVILEGED_NODEC_RUNNER")
    if source_proc_running():
        raise RuntimeError("NODEC_SOURCE_VM906_QEMU_RUNNING")
    if os.path.exists("/run/qemu-server/906.pid"):
        raise RuntimeError("NODEC_SOURCE_VM906_PID_EXISTS")
    note("NODEC_VM906_PROCESS_STOPPED_CONFIRMED=yes")

def nodea_gate():
    gate=r'''
set -Eeuo pipefail
test "$(hostname -s)" = nodea
test "$(qm status 906)" = 'status: stopped'
test "$(qm config 906 | sed -n 's/^name: //p')" = ha-security
test "$(qm config 906 | sed -n 's/^onboot: //p')" = 0
test "$(qm config 906 | sed -n 's/^cores: //p')" = 2
test "$(qm config 906 | sed -n 's/^memory: //p')" = 2048
qm config 906 | grep -Eq '^scsi0: vmdata:vm-906-disk-[0-9]+'
qm config 906 | grep -Eq '^net0: '
if qm config 906 | grep -Eq '^lock:'; then exit 74; fi
test "$(free -m | awk '/^Mem:/ {print $7}')" -ge 2500
test "$(zfs list -Hp -o available vmdata)" -ge 10737418240
zfs list -H vmdata/vm-906-disk-1 >/dev/null
echo "NODEA_DEST_VM906_START_GATE_OK"
'''
    if "NODEA_DEST_VM906_START_GATE_OK" not in remote(gate,45):
        raise RuntimeError("NODEA_PRECHECK_MARKER_MISSING")
    note("NODEA_VM906_START_PREFLIGHT_PASSED=yes")

def start_nodea():
    # One operation only, does not change onboot until Node C onboot is fenced.
    script=r'''
set -Eeuo pipefail
test "$(hostname -s)" = nodea
test "$(qm status 906)" = "status: stopped"
test "$(qm config 906 | sed -n 's/^onboot: //p')" = 0
timeout 105 qm start 906 >/dev/null
test "$(qm status 906)" = 'status: running'
test "$(qm config 906 | sed -n 's/^onboot: //p')" = 0
echo "VM906_NODEA_STARTED_CONFIRM"
'''
    if "VM906_NODEA_STARTED_CONFIRM" not in remote(script,135):
        raise RuntimeError("NODEA_START_POSTCONDITION_UNKNOWN")
    note("NODEA_VM906_RUNNING=yes")
    note("NODEA_VM906_ONBOOT_STILL_DISABLED=yes")

def target_health():
    # DNS first. Do not output the resolved addresses.
    check=r'''
python3 - <<'PY'
import socket
import urllib.request
import urllib.error
name="ha-security.home.arpa"
try:
 with socket.create_connection((name,8123),timeout=3):
  pass
except OSError:
 raise SystemExit(1)
try:
 req=urllib.request.Request("http://"+name+":8123/",method="GET")
 with urllib.request.urlopen(req,timeout=5) as response:
  code=response.status
except urllib.error.HTTPError as e:
 code=e.code
except Exception:
 raise SystemExit(2)
if code in (200,301,302,303,307,308,401,403):
 print("HA_SECURITY_HTTP_READY")
else:
 raise SystemExit(3)
PY
'''
    for n in range(46):
        # Old VM stays fenced during acceptance; fail if it reappears.
        if source_proc_running() or os.path.exists("/run/qemu-server/906.pid"):
            note("SOURCE_NODEC_REAPPEARED_DURING_CHECK=yes")
            # Prioritize a single controller. Keep original running, stop new VM.
            remote("qm stop 906 --timeout 70 >/dev/null; test \"$(qm status 906)\" = 'status: stopped'",120)
            raise RuntimeError("NODEC_SOURCE_REAPPEARED_NODEA_STOPPED")
        state=remote("qm status 906",15)
        if state.strip()!="status: running":
            raise RuntimeError("DESTINATION_STOPPED_UNEXPECTEDLY")
        try:
            if "HA_SECURITY_HTTP_READY" in remote(check,22):
                note("HA_SECURITY_DNS_HTTP_READY=yes")
                return True
        except RuntimeError:
            pass
        if n<45:
            time.sleep(8)
    note("HA_SECURITY_DNS_HTTP_READY=no")
    note("MANUAL_GUEST_NETWORK_OR_HA_INSPECTION_NEEDED=yes")
    return False

def main():
    try:
        source_fenced()
        nodea_gate()
        source_fenced()
        start_nodea()
        source_fenced()
        ready=target_health()
        note("NODEC_SOURCE_VM_PRESERVED=yes")
        note("NFS_VM906_ARCHIVE_PRESERVED=yes")
        note("NODEC_SOURCE_ONBOOT_FENCING_NOT_VERIFIED=yes")
        note("NODEA_ONBOOT_LEFT_DISABLED_UNTIL_FENCING=yes")
        note("RESTORED_VM906_ACTIVE_ON_NODEA=yes")
        note("FULL_ALARM_ESPHOME_END_TO_END_VALIDATION_REQUIRED=yes")
        if not ready:
            sys.exit(2)
    except RuntimeError as e:
        note("CUTOVER_BLOCKED_OR_INCOMPLETE="+str(e))
        sys.exit(1)

if __name__=="__main__":
    main()
