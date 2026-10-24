#!/usr/bin/env python3
"""Transactional, token-free activation of the staged HA-General observer.

This MUST only be launched after explicit authorization to restart Core.
Never prints host/device identities, HA config, passwords, local keys, or tokens.
Makes a full byte-for-byte backup of changed configuration.yaml. Uses optimistic
hash guards, HA core check, health/report validation, and guarded rollback.
"""
from __future__ import annotations

import argparse
import base64
import json
import sys
import time
from pathlib import Path
sys.path.insert(0,"gateway/arrival_lighting")
from readiness_probe import ssh_host

VM="905"
GUEST=r'''
import hashlib,json,os,pathlib,re,shutil,stat,sys,time
root=pathlib.Path("/config")
private=root/".jns_tuya_freedom"
config=root/"configuration.yaml"
component=root/"custom_components"/"jns_tuya_freedom"
staged=private/"staged_observer"/"jns_tuya_freedom"
txn=private/"observer-activation"
key_re=re.compile(r"(?m)^jns_tuya_freedom\s*:")
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def safe():
    if private.is_symlink() or not private.is_dir():
        raise RuntimeError("missing_private_dir")
    if stat.S_IMODE(private.stat().st_mode)!=0o700:
        raise RuntimeError("invalid_private_dir_permissions")
    if not config.is_file() or config.is_symlink():
        raise RuntimeError("unexpected_home_assistant_config")
    if (root/"custom_components").is_symlink():
        raise RuntimeError("unsafe_custom_components_path")
    if not (root/"custom_components").is_dir():
        raise RuntimeError("custom_components_missing")
    if not staged.is_dir() or staged.is_symlink():
        raise RuntimeError("staged_observer_missing")
    for name in ("__init__.py","manifest.json"):
        f=staged/name
        if not f.is_file() or f.is_symlink():
            raise RuntimeError("staged_observer_file_missing")
    compile((staged/"__init__.py").read_bytes(),str(staged/"__init__.py"),"exec")
    manifest=json.loads((staged/"manifest.json").read_bytes())
    if manifest.get("domain")!="jns_tuya_freedom":
        raise RuntimeError("staged_manifest_domain_mismatch")
    if component.exists() or component.is_symlink():
        raise RuntimeError("component_already_present")
    if txn.exists() or txn.is_symlink():
        raise RuntimeError("previous_transaction_must_be_reviewed")
    raw=config.read_bytes()
    if key_re.search(raw.decode("utf-8")):
        raise RuntimeError("yaml_observer_already_present")
    if os.statvfs(str(root)).f_bavail*os.statvfs(str(root)).f_frsize<256*1024*1024:
        raise RuntimeError("insufficient_config_free_space")
    # Stage file digests supplied by checked-out repo, not trusting stale staging.
    if sha(staged/"__init__.py")!=sys.argv[2] or sha(staged/"manifest.json")!=sys.argv[3]:
        raise RuntimeError("staged_content_not_current")
    return raw
def atomic_write(path,data,mode=0o600):
    temp=path.with_name(path.name+".jns-new")
    flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,"O_NOFOLLOW",0)
    fd=os.open(str(temp),flags,mode)
    try:
        with os.fdopen(fd,"wb") as f:
            f.write(data);f.flush();os.fsync(f.fileno())
        os.replace(temp,path)
        os.chmod(path,mode)
    finally:
        if temp.exists():temp.unlink()
def execute():
    action=sys.argv[1]
    if action=="inspect":
        raw=safe()
        return {"phase":"PREFLIGHT_SAFE","staged_verified":True,
                "no_existing_component":True,"no_existing_yaml_key":True,
                "config_size_bytes":len(raw),"backup_required":True}
    if action=="install":
        raw=safe()
        original_mode=stat.S_IMODE(config.stat().st_mode)
        txn.mkdir(mode=0o700)
        try:
            txn.chmod(0o700)
            atomic_write(txn/"original_configuration.yaml",raw,0o600)
            append=b"" if raw.endswith(b"\n") else b"\n"
            patched=raw+append+b"\n# JNS token-free Tuya Local observer (read-only)\njns_tuya_freedom:\n"
            journal={"schema":1,"status":"backup_saved",
                     "old_sha256":hashlib.sha256(raw).hexdigest(),
                     "new_sha256":hashlib.sha256(patched).hexdigest(),
                     "original_mode":original_mode,
                     "staged_files":{"__init__.py":sys.argv[2],"manifest.json":sys.argv[3]}}
            atomic_write(txn/"journal.json",json.dumps(journal,sort_keys=True).encode()+b"\n")
            # Optimistic second guard in case YAML changes after preflight.
            if sha(config)!=journal["old_sha256"]:
                raise RuntimeError("config_changed_during_install")
            component.mkdir(mode=0o755)
            for name in ("__init__.py","manifest.json"):
                atomic_write(component/name,(staged/name).read_bytes(),0o644)
            atomic_write(config,patched,original_mode)
            journal["status"]="installed_not_restarted"
            atomic_write(txn/"journal.json",json.dumps(journal,sort_keys=True).encode()+b"\n")
            return {"phase":"INSTALLED_NOT_RESTARTED","config_backup_saved":True,
                    "observer_installed":True,"only_yaml_and_component_changed":True}
        except Exception:
            # The runner will call rollback; no Core restart is attempted here.
            raise
    if action=="rollback":
        if not txn.is_dir() or txn.is_symlink():
            raise RuntimeError("no_safe_transaction_for_rollback")
        journal=json.loads((txn/"journal.json").read_text())
        backup=txn/"original_configuration.yaml"
        if not backup.is_file() or sha(backup)!=journal["old_sha256"]:
            raise RuntimeError("backup_integrity_failed")
        old=backup.read_bytes()
        current=sha(config)
        if current not in (journal["old_sha256"],journal["new_sha256"]):
            raise RuntimeError("configuration_changed_by_another_writer")
        if component.is_dir() and not component.is_symlink():
            for name,expected in journal["staged_files"].items():
                file=component/name
                if not file.is_file() or file.is_symlink() or sha(file)!=expected:
                    raise RuntimeError("observer_component_modified_since_install")
            # __pycache__ may be created by HA import. Only delete it if it
            # contains regular .pyc files and no symlinks.
            cache=component/"__pycache__"
            if cache.exists():
                if cache.is_symlink() or not cache.is_dir():
                    raise RuntimeError("observer_cache_unsafe")
                for file in cache.iterdir():
                    if file.is_symlink() or not file.is_file() or file.suffix!=".pyc":
                        raise RuntimeError("observer_cache_unexpected_contents")
                    file.unlink()
                cache.rmdir()
            (component/"__init__.py").unlink()
            (component/"manifest.json").unlink()
            component.rmdir()
        elif component.exists() or component.is_symlink():
            raise RuntimeError("observer_component_not_regular_directory")
        if current==journal["new_sha256"]:
            atomic_write(config,old,int(journal["original_mode"]))
        journal["status"]="rolled_back"
        atomic_write(txn/"journal.json",json.dumps(journal,sort_keys=True).encode()+b"\n")
        return {"phase":"ROLLED_BACK_FILES","original_config_restored":sha(config)==journal["old_sha256"],
                "observer_component_removed":not component.exists()}
    if action=="verify":
        if not txn.is_dir() or txn.is_symlink():
            raise RuntimeError("activation_transaction_missing")
        journal=json.loads((txn/"journal.json").read_text())
        if sha(config)!=journal["new_sha256"]:
            raise RuntimeError("active_configuration_hash_mismatch")
        report=private/"latest-live.json"
        if not report.is_file() or report.is_symlink():
            return {"phase":"NOT_YET_OBSERVED"}
        data=json.loads(report.read_bytes())
        created=data.get("generated_utc","")
        try:
            from datetime import datetime,timezone
            ts=datetime.fromisoformat(created)
            age=(datetime.now(timezone.utc)-ts).total_seconds()
        except (ValueError,TypeError):
            age=-1
        counts=data.get("aggregate") or {}
        if data.get("mode")!="in_process_read_only" or not 0<=age<=210:
            return {"phase":"NOT_YET_OBSERVED","report_is_current":False}
        if counts.get("unique_physical_cloud_devices")!=12 or counts.get("with_existing_local_entry")!=5 or counts.get("still_needing_local_onboarding")!=7:
            return {"phase":"REPORT_COUNTS_DIFFER","aggregate":counts}
        return {"phase":"OBSERVER_ACTIVE","report_is_current":True,"aggregate":counts,
                "report_private":True,"wan_offline_tested":False}
    raise RuntimeError("unsupported_action")
try:print(json.dumps(execute(),sort_keys=True))
except Exception as err:
    print(json.dumps({"phase":"BLOCKED","reason":str(err)[:80]}))
    raise SystemExit(2)
'''
def guest(args,limit=140):
    result=json.loads(ssh_host("nodeb",["qm","guest","exec",VM,"--",*args]))
    expiry=time.monotonic()+limit
    while not result.get("exited"):
        if not isinstance(result.get("pid"),int) or time.monotonic()>expiry:
            raise RuntimeError("vm905_guest_agent_timeout")
        time.sleep(3)
        result=json.loads(ssh_host("nodeb",["qm","guest","exec-status",VM,str(result["pid"])]))
    return result

def in_core(action,digests,limit=90):
    source="exec(__import__('base64').b64decode('"+base64.b64encode(GUEST.encode()).decode()+"'))"
    res=guest(["docker","exec","homeassistant","python3","-c",source,
               action,digests["__init__.py"],digests["manifest.json"]],limit)
    try:
        status=json.loads((res.get("out-data") or "").strip())
    except (ValueError,AttributeError):
        raise RuntimeError("ha_guest_observer_no_sanitised_report")
    print("JNS_TUYA_OBSERVER_"+action.upper(),json.dumps(status,sort_keys=True),flush=True)
    if res.get("exitcode")!=0 or status.get("phase")=="BLOCKED":
        raise RuntimeError("observer_"+action+"_blocked_"+str(status.get("reason","unknown")))
    return status

def cli(*args,limit=360):
    r=guest(["ha",*args],limit)
    ok=r.get("exitcode")==0
    # Never print the HA error text: config might contain secrets.
    print("JNS_TUYA_CORE_CLI",json.dumps({"action":" ".join(args),
                                         "exit_ok":ok},sort_keys=True),flush=True)
    return ok

def probe(digests):
    status=ssh_host("nodeb",["qm","status",VM])
    if "running" not in status:
        raise RuntimeError("vm905_not_running")
    return in_core("inspect",digests)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--apply",action="store_true")
    args=parser.parse_args()
    comp=Path("gateway/tuya_freedom/component")
    import hashlib
    digests={n:hashlib.sha256((comp/n).read_bytes()).hexdigest()
             for n in ("__init__.py","manifest.json")}
    probe(digests)
    if not cli("core","check",limit=340):
        raise RuntimeError("baseline_core_check_failed_no_changes")
    print("JNS_TUYA_BASELINE_CONFIGURATION_VALID",flush=True)
    if not args.apply:
        print("JNS_TUYA_PREFLIGHT_PASSED_NO_CHANGES",flush=True)
        return
    applied=False
    restarted=False
    try:
        in_core("install",digests)
        applied=True
        if not cli("core","check",limit=340):
            raise RuntimeError("post_install_core_check_failed")
        print("JNS_TUYA_POSTINSTALL_CONFIGURATION_VALID",flush=True)
        # A single Core restart, not a VM shutdown or HA OS restart.
        if not cli("core","restart",limit=300):
            raise RuntimeError("core_restart_command_failed")
        restarted=True
        until=time.monotonic()+260
        last=None
        while time.monotonic()<until:
            time.sleep(12)
            try:
                if not cli("core","info",limit=45):
                    continue
                last=in_core("verify",digests,limit=55)
                if last.get("phase")=="OBSERVER_ACTIVE":
                    print("JNS_TUYA_TOKENFREE_DEPLOY_VERIFIED",flush=True)
                    return
                if last.get("phase")=="REPORT_COUNTS_DIFFER":
                    raise RuntimeError("physical_device_counts_changed_review_required")
            except RuntimeError:
                continue
        raise RuntimeError("observer_no_valid_fresh_report_after_core_restart")
    except Exception as err:
        print("JNS_TUYA_OBSERVER_ACTIVATION_FAILED",type(err).__name__,str(err)[:105],flush=True)
        if applied:
            rollback=in_core("rollback",digests,limit=90)
            if not cli("core","check",limit=340):
                raise RuntimeError("original_config_check_failed_after_rollback")
            if restarted:
                if not cli("core","restart",limit=300):
                    raise RuntimeError("restored_config_reboot_failed")
                # Report restoration attempt, not speculative operational success.
                print("JNS_TUYA_OBSERVER_ROLLBACK_CORE_RESTART_ISSUED",flush=True)
            print("JNS_TUYA_OBSERVER_ROLLED_BACK",flush=True)
        raise

if __name__=="__main__":
    try:main()
    except Exception as err:
        print("JNS_TUYA_TOKENFREE_DEPLOY_BLOCKED",type(err).__name__,str(err)[:110],flush=True)
        raise SystemExit(1)
