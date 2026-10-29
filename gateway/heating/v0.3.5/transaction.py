#!/usr/bin/env python3
"""JNS HA-General VM905 heating v0.3.5 guarded filesystem transaction.

No network calls, HA services, thermostat commands, restart or reload.
All production activation must be invoked by a separately authorised,
root-owned JNS deployment handler. The public CI workflow calls only
preflight and the offline fixtures.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile

DOMAIN = "jns_heating_zones"
OLD_VERSION = "0.3.4"
NEW_VERSION = "0.3.5"
OLD_THERMAL_SHA = "44054f9172e3c9e2e944240b5369b49d9735d8349fb7ca2dd0a2a782d7c8a4f8"
EXPECTED_UNCHANGED = {
    "__init__.py": "81160fd7e7a73cf8319d1787b8e295c464f7b1ae407db11fd4823937db901d79",
    "coordinator.py": "9407ac6a9d75b772c4fe833b53cca1c7d565c61ebe40bdc5e6c8f72e609a0b74",
    "sensor.py": "f917e70602765c67fe0ed7597ea3e87cc9920b82ac773b7c2c2f2d5ce4ce9a01",
}
EXPECTED_ENTITIES = {
    "sensor.lyric_home_heating_thermal_learning",
    "sensor.lyric_home_heating_projected_temperature_in_60_minutes",
}
STORAGE_PATTERN = re.compile(r"^jns_heating_zone_[A-Za-z0-9_-]+$")
STAGE_PATTERN = re.compile(r"^v035-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}$")
SNAPSHOT = ".jns_heating_backups"


class GuardError(RuntimeError):
    pass


def insist(condition, message):
    if not condition:
        raise GuardError(message)


def sha(blob):
    return hashlib.sha256(blob).hexdigest()


def secure_path(path, root):
    root = Path(root).resolve(strict=True)
    path = Path(path)
    insist(path.is_relative_to(root), "path escapes approved root")
    cursor = root
    for part in path.relative_to(root).parts:
        cursor = cursor / part
        insist(not cursor.is_symlink(), "symlink in protected path")


def read(path, root):
    secure_path(path, root)
    insist(path.is_file(), "required file absent")
    return path.read_bytes()


def atomic(path, content, root, *, mode=None):
    secure_path(path, root)
    insist(path.parent.is_dir(), "destination directory absent")
    previous = path.stat() if path.exists() else None
    fd, name = tempfile.mkstemp(prefix=".jns-heating-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        if previous:
            os.chmod(name, previous.st_mode & 0o777)
            if hasattr(os, "chown"):
                os.chown(name, previous.st_uid, previous.st_gid)
        else:
            os.chmod(name, mode if mode is not None else 0o600)
        os.replace(name, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def get_paths(root):
    root = Path(root).resolve(strict=True)
    component = root / "custom_components" / DOMAIN
    storage = root / ".storage"
    insist(component.is_dir() and storage.is_dir(), "expected VM905 HA directories absent")
    secure_path(component, root)
    secure_path(storage, root)
    return root, component, storage


def inventory(root, candidate):
    root, comp, storage = get_paths(root)
    expected = comp / "thermal.py"
    source = read(expected, root)
    insist(sha(source) == OLD_THERMAL_SHA, "deployed thermal.py fingerprint changed")
    manifests = read(comp / "manifest.json", root)
    try:
        manifest = json.loads(manifests)
    except ValueError:
        raise GuardError("manifest invalid JSON") from None
    insist(manifest.get("domain") == DOMAIN and manifest.get("version") == OLD_VERSION,
           "installed heating domain/version changed")
    for name, digest in EXPECTED_UNCHANGED.items():
        insist(sha(read(comp / name, root)) == digest,
               "unexpected current integration source: " + name)
    insist(isinstance(candidate, bytes) and candidate.startswith(b'"""JNS Heating Zones thermal learner v0.3.5'),
           "candidate is not identified v0.3.5 learner")
    compile(candidate, str(comp / "thermal.py"), "exec")
    entries = list(storage.iterdir())
    zone_files = sorted(p for p in entries if STORAGE_PATTERN.fullmatch(p.name))
    insist(len(zone_files) >= 1, "no preserved learning stores found")
    store_info = {}
    for p in zone_files:
        blob = read(p, root)
        try:
            obj = json.loads(blob)
            samples = obj["data"]["samples"]
        except (ValueError, KeyError, TypeError):
            raise GuardError("unexpected learning store shape") from None
        insist(isinstance(samples, list), "learning sample list missing")
        insist(all(isinstance(x, dict) and {"at","indoor","outdoor","duty","valid"} <= x.keys()
                   for x in samples), "historical sample schema changed")
        store_info[p.name] = {"sha": sha(blob), "count": len(samples), "size": len(blob)}
    registry = read(storage / "core.entity_registry", root)
    try:
        found = {e["entity_id"] for e in json.loads(registry)["data"]["entities"]}
    except (ValueError, KeyError, TypeError):
        raise GuardError("entity registry unreadable") from None
    insist(EXPECTED_ENTITIES <= found, "heating entities not registered")
    unchanged_hashes = {name: sha(read(comp / name, root)) for name in EXPECTED_UNCHANGED}
    candidate_sha = sha(candidate)
    new_manifest = json.loads(manifests)
    new_manifest["version"] = NEW_VERSION
    updated_manifest = (json.dumps(new_manifest, indent=2, ensure_ascii=False) + "\n").encode()
    demand = len(source) + len(manifests) + sum(v["size"] for v in store_info.values())
    free = shutil.disk_usage(root).free
    insist(free > max(demand*3, 10*1024*1024), "insufficient free space for private backup")
    return {"component":comp,"storage":storage,"original":source,"manifest":manifests,
            "new_manifest":updated_manifest,"stores":store_info,
            "unchanged":unchanged_hashes,"candidate_sha":candidate_sha,
            "candidate":candidate,"root":root}


def backup_root(root):
    root = Path(root)
    folder = root / SNAPSHOT
    secure_path(folder, root)
    if not folder.exists():
        folder.mkdir(mode=0o700)
    insist(folder.is_dir(), "backups root absent")
    os.chmod(folder, 0o700)
    insist(folder.stat().st_mode & 0o077 == 0, "unsafe backup directory permissions")
    return folder


def stage(root, candidate):
    info = inventory(root, candidate)
    backup_dir = backup_root(info["root"])
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    stage_id = f"v035-{stamp}-{info['candidate_sha'][:8]}"
    destination = backup_dir / stage_id
    insist(not destination.exists(), "candidate already staged this second")
    destination.mkdir(mode=0o700)
    try:
        originals = destination / "original"
        originals.mkdir(mode=0o700)
        for name, data in [("thermal.py", info["original"]),
                           ("manifest.json", info["manifest"])]:
            atomic(originals / name, data, info["root"], mode=0o600)
        stores = destination / "stores"
        stores.mkdir(mode=0o700)
        for name, meta in info["stores"].items():
            # Refuse mutable/partial copies; active Store may flush concurrently.
            data = read(info["storage"] / name, info["root"])
            insist(sha(data) == meta["sha"], "learning store changed during snapshot")
            atomic(stores / name, data, info["root"], mode=0o600)
            insist(sha(read(stores / name, info["root"])) == meta["sha"],
                   "learning backup checksum mismatch")
        atomic(destination / "candidate.py", info["candidate"], info["root"], mode=0o600)
        meta = {
            "schema": 1, "stage_id": stage_id, "state": "staged",
            "candidate_sha": info["candidate_sha"],
            "legacy_thermal_sha": sha(info["original"]),
            "legacy_manifest_sha": sha(info["manifest"]),
            "new_manifest_sha": sha(info["new_manifest"]),
            "untouched_integration": info["unchanged"], "stores": info["stores"],
            "target_version": NEW_VERSION, "runtime_reload": False,
        }
        atomic(destination / "state.json", (json.dumps(meta, indent=2,sort_keys=True)+"\n").encode(),
               info["root"],mode=0o600)
        insist(all((destination / "original" / name).exists() for name in
                   ("thermal.py","manifest.json")), "backup incomplete")
        return {"state": "staged", "stage_id": stage_id,
                "store_count": len(info["stores"]), "samples": sum(x["count"] for x in info["stores"].values()),
                "runtime_untouched": True}
    except BaseException:
        shutil.rmtree(destination)
        raise


def stage_files(root, stage_id):
    insist(STAGE_PATTERN.fullmatch(stage_id), "unsafe stage name")
    root, comp, storage = get_paths(root)
    destination = root / SNAPSHOT / stage_id
    secure_path(destination, root)
    insist(destination.is_dir(), "stage is missing")
    raw = read(destination / "state.json", root)
    try:
        meta = json.loads(raw)
    except ValueError:
        raise GuardError("stage metadata damaged") from None
    insist(meta.get("stage_id") == stage_id and meta.get("schema") == 1,
           "wrong stage metadata")
    return root,comp,storage,destination,meta


def check_stage_original(root, comp, storage, destination, meta):
    original = read(destination / "original/thermal.py", root)
    manifest = read(destination / "original/manifest.json", root)
    candidate = read(destination / "candidate.py", root)
    insist(sha(original) == meta["legacy_thermal_sha"] == OLD_THERMAL_SHA,
           "original source snapshot mismatch")
    insist(sha(manifest) == meta["legacy_manifest_sha"], "manifest backup mismatch")
    insist(sha(candidate) == meta["candidate_sha"], "candidate staging checksum mismatch")
    for name, digest in meta["untouched_integration"].items():
        insist(sha(read(comp / name, root)) == digest, "integration changed: "+name)
    for name, record in meta["stores"].items():
        insist(STORAGE_PATTERN.fullmatch(name), "unsafe store name")
        insist(sha(read(destination / "stores" / name, root)) == record["sha"],
               "stored learning backup damaged")
        # Current HA Store may have added observations; never overwrite it.
        current = json.loads(read(storage / name, root))
        insist(isinstance(current["data"]["samples"], list),
               "current learning samples inaccessible")
    return original,manifest,candidate


def commit(root, stage_id, *, approved=False):
    insist(approved, "production commit requires separately authorised gateway approval")
    root,comp,storage,destination,meta = stage_files(root,stage_id)
    insist(meta["state"] == "staged", "stage already applied or rolled back")
    original,manifest,candidate = check_stage_original(root,comp,storage,destination,meta)
    insist(sha(read(comp / "thermal.py", root)) == meta["legacy_thermal_sha"],
           "thermal component changed after staging")
    insist(sha(read(comp / "manifest.json", root)) == meta["legacy_manifest_sha"],
           "manifest changed after staging")
    updated = json.loads(manifest)
    updated["version"] = NEW_VERSION
    target_manifest=(json.dumps(updated,indent=2,ensure_ascii=False)+"\n").encode()
    insist(sha(target_manifest) == meta["new_manifest_sha"], "manifest rendering changed")
    changed = []
    try:
        atomic(comp / "thermal.py", candidate, root)
        changed.append(("thermal.py", original))
        atomic(comp / "manifest.json", target_manifest, root)
        changed.append(("manifest.json", manifest))
        insist(sha(read(comp / "thermal.py",root)) == meta["candidate_sha"],
               "installed candidate verification failed")
        insist(sha(read(comp / "manifest.json",root)) == meta["new_manifest_sha"],
               "installed manifest verification failed")
        meta["state"] = "applied_pending_runtime_verification"
        atomic(destination / "state.json",
               (json.dumps(meta,indent=2,sort_keys=True)+"\n").encode(),root)
    except BaseException:
        for name,old in reversed(changed):
            atomic(comp / name,old,root)
        raise
    return {"state":"applied_pending_runtime_verification","stage_id":stage_id,
            "runtime_reload":False, "heating_controls_unchanged":True}


def verify(root, stage_id):
    root,comp,storage,destination,meta=stage_files(root,stage_id)
    check_stage_original(root,comp,storage,destination,meta)
    if meta["state"]=="staged":
        insist(sha(read(comp / "thermal.py",root))==meta["legacy_thermal_sha"],
               "unexpected active thermal source")
        insist(sha(read(comp / "manifest.json",root))==meta["legacy_manifest_sha"],
               "unexpected active integration manifest")
        for directory in (root/SNAPSHOT,destination,destination/"stores",destination/"original"):
            insist(directory.stat().st_mode & 0o077 == 0,"private backup directory permissions unsafe")
        for file in (destination/"candidate.py",destination/"state.json",
                     destination/"original/thermal.py",destination/"original/manifest.json"):
            insist(file.stat().st_mode & 0o077 == 0,"private backup file permissions unsafe")
        for name in meta["stores"]:
            insist((destination/"stores"/name).stat().st_mode & 0o077 == 0,
                   "private learning backup file permissions unsafe")
        return {"state":"staged","runtime_reload":False,"backups_integrity_verified":True}
    if meta["state"]=="applied_pending_runtime_verification":
        insist(sha(read(comp / "thermal.py",root))==meta["candidate_sha"],
               "applied source hash mismatch")
        insist(sha(read(comp / "manifest.json",root))==meta["new_manifest_sha"],
               "applied manifest hash mismatch")
        return {"state":meta["state"],"runtime_reload":False,
                "note":"File verification only: Home Assistant runtime not reloaded"}
    if meta["state"]=="rolled_back":
        insist(sha(read(comp / "thermal.py",root))==meta["legacy_thermal_sha"],
               "rolled-back thermal.py differs from snapshot")
        return {"state":"rolled_back","runtime_reload":False}
    raise GuardError("unrecognised stage state")


def rollback(root,stage_id):
    root,comp,storage,destination,meta=stage_files(root,stage_id)
    insist(meta["state"]=="applied_pending_runtime_verification",
           "rollback allowed only for this pending candidate")
    original,manifest,_=check_stage_original(root,comp,storage,destination,meta)
    insist(sha(read(comp / "thermal.py",root))==meta["candidate_sha"],
           "cannot overwrite a newer thermal component")
    insist(sha(read(comp / "manifest.json",root))==meta["new_manifest_sha"],
           "cannot overwrite a newer manifest")
    atomic(comp / "thermal.py",original,root)
    atomic(comp / "manifest.json",manifest,root)
    meta["state"]="rolled_back"
    atomic(destination / "state.json",
           (json.dumps(meta,indent=2,sort_keys=True)+"\n").encode(),root)
    return {"state":"rolled_back", "learning_store_restored":False,
            "learning_store_preserved":True,"runtime_reload":False}


def cli():
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("preflight","stage","commit","verify","rollback"))
    p.add_argument("--root",default="/config")
    p.add_argument("--candidate")
    p.add_argument("--stage-id")
    # This flag is merely an *additional* acknowledgement: the trusted gateway
    # must enforce real authorisation outside the guest, and is not wired yet.
    p.add_argument("--gateway-authorised",action="store_true")
    args=p.parse_args()
    try:
        if args.action in ("preflight","stage"):
            insist(args.candidate is not None,"candidate file required")
            if args.candidate=="-":
                candidate=globals().get("CANDIDATE_BYTES")
                insist(isinstance(candidate,bytes),"inline candidate missing")
            else:
                candidate=Path(args.candidate).read_bytes()
            if args.action=="preflight":
                info=inventory(args.root,candidate)
                result={"state":"preflight_passed","version":OLD_VERSION,
                    "expected_digest":OLD_THERMAL_SHA,
                    "candidate_digest":info["candidate_sha"],
                    "stores":len(info["stores"]), "configuration_unchanged":True}
            else:
                result=stage(args.root,candidate)
        else:
            insist(args.stage_id is not None,"stage id required")
            if args.action=="verify":
                result=verify(args.root,args.stage_id)
            elif args.action=="commit":
                result=commit(args.root,args.stage_id,approved=args.gateway_authorised)
            else:
                insist(args.gateway_authorised,"rollback requires approved gateway")
                result=rollback(args.root,args.stage_id)
        print("JNS_HEATING_GUARDED",json.dumps(result,sort_keys=True))
    except (GuardError,OSError,KeyError,ValueError,TypeError,SyntaxError) as exc:
        print("JNS_HEATING_BLOCKED",type(exc).__name__,str(exc)[:160])
        sys.exit(2)


if __name__=="__main__":
    cli()
