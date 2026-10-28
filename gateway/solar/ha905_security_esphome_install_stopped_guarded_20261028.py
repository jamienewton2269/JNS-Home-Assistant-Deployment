#!/usr/bin/env python3
"""Prepare the reviewed temporary ESPHome app on VM905, INSTALLED BUT STOPPED.

This deliberately performs NO config-flow calls, no key transfer, no HA Core
restart, no VM power action, and no security device operation. VM906 MUST remain
running throughout. Never use this as authority to begin a security outage.
"""
import base64
import hashlib
import json
import os
import pathlib
import re
import shlex
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).parent / "ha905_security_esphome_handover_app"
FILES = ("config.yaml", "Dockerfile", "run.sh", "flow.py")
SLUG = "local_jns_ha905_security_handover"
SSH = ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
       "-o", "ConnectTimeout=6"]
REMOTE = r"""
import base64,hashlib,json,os,pathlib,shlex,subprocess,sys,time
if os.geteuid()!=0 or os.uname().nodename.split(".")[0]!="nodeb":
    raise SystemExit(70)
SRC="/mnt/data/supervisor/apps/local/jns_ha905_security_handover"
SLUG="local_jns_ha905_security_handover"
FILENAMES=("config.yaml","Dockerfile","run.sh","flow.py")
def note(key,value):
    print("JNS_SECURITY_APP_PREP_"+key+"="+str(value),flush=True)
def fail(reason):
    note("BLOCKED",reason);raise SystemExit(71)
def cmd(argv,timeout=35):
    try:return subprocess.run(argv,capture_output=True,text=True,timeout=timeout)
    except (OSError,subprocess.TimeoutExpired):return None
def guest(argv,timeout=180):
    p=cmd(["qm","guest","exec","905","--",*argv],30)
    if not p or p.returncode: return None
    try:j=json.loads(p.stdout)
    except ValueError:return None
    deadline=time.monotonic()+timeout
    while not j.get("exited") and time.monotonic()<deadline:
        if not j.get("pid"):return None
        time.sleep(1)
        p=cmd(["qm","guest","exec-status","905",str(j["pid"])],25)
        if not p or p.returncode:return None
        try:j=json.loads(p.stdout)
        except ValueError:return None
    return j if j.get("exited") and not j.get("out-truncated") else None
def sh(command,timeout=120):return guest(["sh","-c",command],timeout)
def good(j):return bool(j and j.get("exitcode")==0)
def app_info():
    x=guest(["ha","apps","info",SLUG,"--raw-json","--no-progress"],45)
    if not good(x):return None
    try:
        v=json.loads(x.get("out-data") or "{}")
        return v.get("data") if v.get("result")=="ok" and isinstance(v.get("data"),dict) else None
    except (TypeError,ValueError):return None
def source_active():
    p=cmd(["qm","status","905"],15)
    return bool(p and p.returncode==0 and p.stdout.strip()=="status: running")
if not source_active():fail("vm905_unavailable")
cfg=cmd(["qm","config","905"],20)
if not cfg or cfg.returncode or not any(
    x.strip()=="name: ha-s2-general" for x in cfg.stdout.splitlines()
):fail("vm905_identity")
backup=pathlib.Path("/mnt/pve/NAS/dump/jns-ha-general-consolidation-20261027-v1/MANIFEST.json")
if backup.is_symlink() or not backup.is_file():fail("backup_manifest_missing")
try:
    if not isinstance(json.loads(backup.read_text()),dict):fail("backup_manifest_invalid")
except (OSError,ValueError,TypeError):fail("backup_manifest_unreadable")
check='''import pathlib,json
p=pathlib.Path("/config/packages/jns_ha_security_native_cutover_20261028_v2.yaml")
if not p.is_file() or p.is_symlink():raise SystemExit(1)
s=p.read_text()
if s.count("initial_state: false")!=6 or "alarm_control_panel:" not in s:raise SystemExit(2)
print("JNS_NATIVE_SECURITY_DISABLED=yes")
'''
j=guest(["docker","exec","homeassistant","python3","-c",check],45)
if not good(j) or "JNS_NATIVE_SECURITY_DISABLED=yes" not in (j.get("out-data") or ""):
    fail("six_disabled_automations_not_verified")
j=guest(["ha","core","info"],50)
if not good(j):fail("vm905_core_unhealthy")
pre=app_info()
if pre and pre.get("installed") is True:
    if pre.get("version")=="0.1.0" and pre.get("state")=="stopped" and pre.get("repository")=="local":
        note("INSTALLED_STOPPED","already_present")
        raise SystemExit(0)
    fail("existing_app_collision")
if not good(sh("test -d /mnt/data/supervisor/apps/local && test ! -L "+
                shlex.quote(SRC),30)):
    fail("supervisor_layout_or_source_symlink")
retained=good(sh("test -d "+shlex.quote(SRC)+" && test ! -L "+
                 shlex.quote(SRC),30))
if not retained and not good(sh("test ! -e "+shlex.quote(SRC)+" && test ! -L "+
                                shlex.quote(SRC),30)):
    fail("local_source_collision")
obj=json.loads(sys.stdin.buffer.read(100000))
if obj.get("target_vm")!=905 or set(obj.get("files",{}))!=set(FILENAMES):
    fail("wrong_payload")
files={}
for k,v in obj["files"].items():
    raw=base64.b64decode(v["base64"],validate=True)
    if len(raw)>20000 or hashlib.sha256(raw).hexdigest()!=v["sha256"]:fail("bad_source_checksum")
    files[k]=raw
if b"homeassistant_api: true" not in files["config.yaml"] or b"boot: manual_only" not in files["config.yaml"]:
    fail("unsafe_manifest")
if b"ghcr.io/home-assistant/base-python:3.14-alpine3.24" not in files["Dockerfile"]:
    fail("unreviewed_base_image")
if not retained and not good(sh("mkdir "+shlex.quote(SRC),30)):
    fail("source_directory_creation")
# Retained source can be reused only after validating EVERY exact original byte.
# Never overwrite or delete source during an unconfirmed Supervisor build.
if retained:
    expected=" ".join(FILENAMES)
    check="test \"$(ls -1 "+shlex.quote(SRC)+" | sort | tr '\\n' ' ')\" = "+shlex.quote(" ".join(sorted(FILENAMES))+" ")
    if not good(sh(check,30)):fail("retained_source_extra_or_missing_files")
for name,raw in files.items():
    path=shlex.quote(SRC+"/"+name)
    if not retained:
        b64=base64.b64encode(raw).decode("ascii")
        statement="printf '%s' "+shlex.quote(b64)+" | base64 -d > "+path
        if not good(sh(statement,40)):fail("source_copy_failed_preserved")
    verify="test \"$(sha256sum "+path+" | cut -d' ' -f1)\" = "+shlex.quote(hashlib.sha256(raw).hexdigest())
    if not good(sh(verify,30)):fail("source_hash_failed_preserved")
note("SOURCE","retained_hash_verified" if retained else "hash_verified")
reload_result=guest(["ha","store","reload","--no-progress"],150)
if not good(reload_result):
    reload_result=guest(["ha","store","reload"],150)
if not good(reload_result):
    fail("supervisor_store_reload_failed_source_preserved")
note("STORE","refreshed")
# Installing does not start this boot:manual_only, startup:once app.
# Supervisor CLI can return ambiguous success; state is the actual proof.
installed_cmd=guest(["ha","apps","install",SLUG,"--no-progress","--raw-json"],400)
note("INSTALL_CLI_RETURNED",str(installed_cmd is not None).lower())
info=None
for _ in range(35):
    info=app_info()
    if info and info.get("installed") is True and info.get("version")=="0.1.0":
        break
    time.sleep(3)
if not info or info.get("installed") is not True or info.get("version")!="0.1.0":
    fail("installation_not_verified_keep_source_for_review")
if info.get("state")!="stopped" or info.get("repository")!="local":
    fail("unexpected_started_or_nonlocal_app")
note("INSTALLED_STOPPED","verified")
note("NO_CONFIG_FLOW_OR_SECURITY_OUTPUTS","yes")
"""
def ssh(host,args,stdin=None,timeout=45):
    try:return subprocess.run(SSH+[host,shlex.join(args)],input=stdin,
                              capture_output=True,text=True,timeout=timeout)
    except (OSError,subprocess.TimeoutExpired):return None
def vm_ok(host,vm,name):
    a=ssh(host,["qm","status",str(vm)])
    b=ssh(host,["qm","config",str(vm)])
    return bool(a and b and a.returncode==b.returncode==0
                and a.stdout.strip()=="status: running"
                and re.search(r"^name:\s*"+re.escape(name)+r"\s*$",b.stdout,re.M))
def main():
    if os.uname().nodename.split(".")[0]!="nodec":
        print("JNS_SECURITY_APP_PREP_BLOCKED=wrong_runner");return 1
    if not vm_ok("nodea",906,"ha-security") or not vm_ok("nodeb",905,"ha-s2-general"):
        print("JNS_SECURITY_APP_PREP_BLOCKED=owner_or_target_state");return 1
    files={}
    for name in FILES:
        path=ROOT/name
        if not path.is_file() or path.is_symlink():
            print("JNS_SECURITY_APP_PREP_BLOCKED=missing_app_source");return 1
        data=path.read_bytes()
        files[name]={"base64":base64.b64encode(data).decode("ascii"),
                     "sha256":hashlib.sha256(data).hexdigest()}
    payload=json.dumps({"target_vm":905,"files":files})
    remote=base64.b64encode(REMOTE.encode()).decode("ascii")
    args=["python3","-u","-c","exec(__import__('base64').b64decode("+repr(remote)+"))"]
    r=ssh("nodeb",args,stdin=payload,timeout=740)
    for line in (r.stdout if r else "").splitlines():
        if line.startswith("JNS_SECURITY_APP_PREP_"):print(line,flush=True)
    if not r or r.returncode:
        if r:
            print("JNS_SECURITY_APP_PREP_REMOTE_EXIT="+str(r.returncode),flush=True)
            error=r.stderr or ""
            diagnosis=("python_syntax" if "SyntaxError:" in error else
                       "python_name" if "NameError:" in error else
                       "python_import" if "ImportError:" in error else
                       "python_indentation" if "IndentationError:" in error else
                       "ssh_auth" if "Permission denied" in error else
                       "ssh_transport" if "Connection refused" in error or "Host key verification failed" in error else
                       "remote_unclassified")
            print("JNS_SECURITY_APP_PREP_DIAGNOSTIC="+diagnosis,flush=True)
        print("JNS_SECURITY_APP_PREP_BLOCKED=installation_or_validation_incomplete");return 1
    if not vm_ok("nodea",906,"ha-security"):
        print("JNS_SECURITY_APP_PREP_BLOCKED=source_owner_changed");return 1
    print("JNS_SECURITY_APP_PREP_RESULT=installed_stopped_source_vm906_untouched",flush=True)
    return 0
if __name__=="__main__":sys.exit(main())
