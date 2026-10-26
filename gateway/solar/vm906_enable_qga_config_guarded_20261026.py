#!/usr/bin/env python3
"""Guarded host-side QGA enablement for active HA-Security VM906.
Config only. Does NOT stop, start, reboot or modify guest files.
Runs from Node C GitHub runner through existing trusted SSH path to Node A.
"""
import base64,json,os,shlex,subprocess,sys
REMOTE=r'''
import os,re,json,subprocess,hashlib
from pathlib import Path
def run(args,timeout=20):
    try:return subprocess.run(args,capture_output=True,text=True,timeout=timeout)
    except (OSError,subprocess.TimeoutExpired):return None
def fail(code):print("JNS_VM906_QGA_CONFIG_BLOCKED="+code);raise SystemExit(1)
if os.geteuid()!=0 or os.uname().nodename.split(".")[0]!="nodea":fail("not_authorised_nodea_root")
s=run(["qm","status","906"])
if not s or s.returncode!=0 or s.stdout.strip()!="status: running":fail("VM906_not_running")
v=run(["qm","config","906"])
if not v or v.returncode!=0:fail("config_unreadable")
cfg=v.stdout
if not re.search(r"^name:\s*ha-security\s*$",cfg,re.M):fail("wrong_guest_identity")
if re.search(r"^lock:",cfg,re.M):fail("guest_locked")
if re.search(r"^agent:\s*(?:enabled=)?1(?:\s|,|$)",cfg,re.M):
    p=run(["qm","agent","906","ping"],9)
    print("JNS_VM906_QGA_CONFIG_STATUS="+json.dumps({
        "agent_config_enabled":True,
        "agent_responding":bool(p and p.returncode==0),
        "state":"pre_existing",
        "reboot_performed":False},sort_keys=True))
    raise SystemExit(0)
if re.search(r"^agent:",cfg,re.M):
    fail("different_existing_agent_setting_requires_review")
# A private, restrictive backup of Proxmox config only (no guest disk touches).
source=Path("/etc/pve/qemu-server/906.conf")
if not source.is_file() or source.is_symlink():fail("config_source_missing")
blob=source.read_bytes()
if not (100<len(blob)<65536):fail("config_size_outside_expected")
store=Path("/var/lib/jns-solar/ha-security-qga-20261026")
store.mkdir(parents=True,exist_ok=True,mode=0o700)
os.chmod(store,0o700)
backup=store/"vm906-before-qga.conf"
try:
 with backup.open("xb") as f:f.write(blob)
except FileExistsError:
 if backup.read_bytes()!=blob:fail("private_previous_config_conflict")
os.chmod(backup,0o600)
if hashlib.sha256(backup.read_bytes()).digest()!=hashlib.sha256(blob).digest():fail("backup_hash_failed")
a=run(["qm","set","906","--agent","enabled=1"],20)
if not a or a.returncode!=0:fail("qm_set_failed")
v=run(["qm","config","906"])
s=run(["qm","status","906"])
if not v or v.returncode!=0 or not re.search(r"^agent:\s*(?:enabled=)?1(?:\s|,|$)",v.stdout,re.M):fail("config_not_enabled")
if not s or s.returncode!=0 or s.stdout.strip()!="status: running":fail("unexpected_guest_state")
p=run(["qm","agent","906","ping"],9)
print("JNS_VM906_QGA_CONFIG_STATUS="+json.dumps({
 "agent_config_enabled":True,
 "agent_responding":bool(p and p.returncode==0),
 "state":"updated",
 "private_config_backup_verified":True,
 "reboot_performed":False,
 "guest_files_untouched":True,
 "cold_start_required_if_no_ping":not bool(p and p.returncode==0)},sort_keys=True))
'''
def main():
    encoded=base64.b64encode(REMOTE.encode()).decode()
    cmd=["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes",
         "-o","ConnectTimeout=5","nodea",
         shlex.join(["python3","-c","exec(__import__('base64').b64decode('"+encoded+"'))"])]
    try:p=subprocess.run(cmd,capture_output=True,text=True,timeout=75)
    except (OSError,subprocess.TimeoutExpired):
        print("JNS_VM906_QGA_REMOTE_TIMEOUT");raise SystemExit(1)
    for l in p.stdout.splitlines():
        if l.startswith(("JNS_VM906_QGA_CONFIG_STATUS=","JNS_VM906_QGA_CONFIG_BLOCKED=")):
            print(l,flush=True)
    if p.returncode:raise SystemExit(p.returncode)
if __name__=="__main__":main()
