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
def app_installed():
    x=guest(["ha","apps","list","--no-progress","--raw-json"],50)
    if not good(x):return False
    try:
        resp=json.loads(x.get("out-data") or "{}")
        data=resp.get("data",{})
        apps=data.get("apps",data.get("addons")) if isinstance(data,dict) else data
        return bool(resp.get("result")=="ok" and isinstance(apps,list) and
                    sum(a.get("slug")==SLUG and a.get("installed") is not False
                        for a in apps if isinstance(a,dict))==1)
    except (ValueError,TypeError,AttributeError):return False
def store_catalog_has_local_app():
    x=guest(["ha","store","info",SLUG,"--no-progress","--raw-json"],75)
    if not good(x):return False
    try:
        reply=json.loads(x.get("out-data") or "{}")
        data=reply.get("data",{})
        apps=data.get("addons") if isinstance(data,dict) else None
        return bool(reply.get("result")=="ok" and isinstance(apps,list) and
                    sum((a.get("slug") if isinstance(a,dict) else a)==SLUG
                        for a in apps)==1)
    except (ValueError,TypeError,AttributeError):return False
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
if pre and pre.get("version")=="0.1.1" and pre.get("state")=="stopped" and pre.get("repository")=="local" and app_installed():
    note("INSTALLED_STOPPED","already_present_verified_by_state_version")
    raise SystemExit(0)
if pre and pre.get("installed") is True:
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
    def current_is(hashes):
        return all(good(sh("test \"$(sha256sum "+
            shlex.quote(SRC+"/"+name)+" | cut -d' ' -f1)\" = "+
            shlex.quote(hashes[name]),30)) for name in FILENAMES)
    new_hashes={name:hashlib.sha256(files[name]).hexdigest() for name in FILENAMES}
    if not current_is(new_hashes):
        old=obj.get("previous_hashes",{})
        if set(old)!=set(FILENAMES) or not current_is(old):
            fail("retained_source_drift_not_pinned_original")
        # Supervisor's ACTUAL installed inventory must show no active app.
        q=guest(["ha","apps","list","--no-progress","--raw-json"],55)
        try:
            data=json.loads(q.get("out-data") or "{}") if good(q) else {}
            section=data.get("data",{})
            apps=section.get("apps",section.get("addons")) if isinstance(section,dict) else section
            safe=(data.get("result")=="ok" and isinstance(apps,list)
                  and not any(a.get("slug")==SLUG and a.get("installed") is not False
                  for a in apps if isinstance(a,dict)))
        except (TypeError,ValueError,AttributeError):safe=False
        if not safe:fail("old_app_still_installed_or_inventory_unknown")
        share="/mnt/data/supervisor/share"
        stage=share+"/jns-security-app-v011-stage-20261028"
        backup=share+"/jns-security-app-v010-source-backup-20261028"
        secret=share+"/jns-security-handover-20261028/enrolment.json"
        if not good(sh("test ! -e "+shlex.quote(secret)+
               " && test ! -L "+shlex.quote(secret)+
               " && test ! -e "+shlex.quote(stage)+
               " && test ! -L "+shlex.quote(stage)+
               " && test ! -e "+shlex.quote(backup)+
               " && test ! -L "+shlex.quote(backup),40)):
            fail("upgrade_stage_collision_or_private_secret_present")
        if not good(sh("mkdir "+shlex.quote(stage),40)):fail("upgrade_stage_create")
        for name,raw in files.items():
            dest=shlex.quote(stage+"/"+name)
            enc=base64.b64encode(raw).decode()
            if not good(sh("printf '%s' "+shlex.quote(enc)+" | base64 -d > "+dest,45)):
                fail("upgrade_stage_copy")
            if not good(sh("test \"$(sha256sum "+dest+" | cut -d' ' -f1)\" = "+
                          shlex.quote(new_hashes[name]),30)):
                fail("upgrade_stage_hash_mismatch")
        # Move old reviewed source OUT of the Supervisor's local catalogue,
        # preserving all files. On failure, restore the original in place.
        command=("mv "+shlex.quote(SRC)+" "+shlex.quote(backup)+
                 " && { mv "+shlex.quote(stage)+" "+shlex.quote(SRC)+
                 " || { mv "+shlex.quote(backup)+" "+shlex.quote(SRC)+"; exit 1; }; }")
        if not good(sh(command,60)):fail("source_switch_failed_original_preserved_or_fenced")
        if not current_is(new_hashes):fail("source_switch_new_hash_not_verified")
        note("SOURCE_UPGRADE","pinned_v010_backed_up_v011_hash_verified")
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
    if not store_catalog_has_local_app():
        fail("supervisor_store_reload_failed_and_local_addon_not_catalogued")
    note("STORE","already_indexed_reload_unavailable")
else:
    note("STORE","refreshed")
# Installing does not start this boot:manual_only, startup:once app.
# Supervisor CLI can return ambiguous success; state is the actual proof.
installed_cmd=guest(["ha","apps","install",SLUG,"--no-progress","--raw-json"],400)
note("INSTALL_CLI_RETURNED",str(installed_cmd is not None).lower())
if installed_cmd:
    note("INSTALL_PROCESS_EXIT",installed_cmd.get("exitcode"))
    try:
        reply=json.loads(installed_cmd.get("out-data") or "{}")
        note("INSTALL_SUPERVISOR_RESULT",str(reply.get("result","unknown"))[:30])
        # Never print API payloads: they may contain private configuration.
        if reply.get("result")!="ok":
            raw=str(reply.get("message",""))+" "+str(reply.get("data",""))
            msg=raw.lower()
            kind=next((k for k in ("not found","repository","version","build","image","network","supervisor","missing","unsupported","already installed")
                      if k in msg),"unclassified")
            note("INSTALL_ERROR_CATEGORY",kind.replace(" ","_"))
    except (TypeError,ValueError):note("INSTALL_SUPERVISOR_RESULT","non_json")
info=None
for _ in range(35):
    info=app_info()
    if info and info.get("version")=="0.1.1" and info.get("state")=="stopped" and info.get("repository")=="local":
        break
    time.sleep(3)
if not info or info.get("version")!="0.1.1" or info.get("state")!="stopped" or info.get("repository")!="local" or not app_installed():
    note("INSTALL_IN_INSTALLED_INVENTORY",str(app_installed()).lower())
    fail("installation_not_verified_keep_source_for_review")
note("INSTALL_IN_INSTALLED_INVENTORY","true")
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
    # The only permitted retained-source upgrade is the byte-exact public
    # v0.1.0 addon previously deployed. Never trust an arbitrary local source.
    baseline={}
    for name in FILES:
        old=subprocess.run(["git","show",
            "b37181c265190c1ed125a32ea02efa7d8abf6b6e:gateway/solar/ha905_security_esphome_handover_app/"+name],
            cwd=ROOT.parents[2],capture_output=True,timeout=25)
        if old.returncode:
            print("JNS_SECURITY_APP_PREP_BLOCKED=pinned_source_unavailable");return 1
        baseline[name]=hashlib.sha256(old.stdout).hexdigest()
    payload=json.dumps({"target_vm":905,"files":files,"previous_hashes":baseline})
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
