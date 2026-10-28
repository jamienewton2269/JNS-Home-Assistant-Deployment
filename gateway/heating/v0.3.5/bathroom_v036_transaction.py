#!/usr/bin/env python3
"""VM905 advisory bathroom v0.3.6 atomic deployment file transaction.

This program is a confined primitive, NOT a deployment authorisation.
Only an independently installed, locally approved and audited root-owned
JNS capability may invoke --commit or --rollback. The existing GitHub
workflow invokes --preflight/--stage/--verify ONLY. No HA restart here.

Updates precisely six files of custom_components/jns_heating_zones:
  coordinator.py, sensor.py, thermal.py, bathroom_reference.py,
  bathroom_runtime.py, manifest.json.
Never touches legacy learning storage, thermostat configuration, credentials,
HA900, VM903 or arbitrary packages.
"""
from __future__ import annotations

import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import uuid

DOMAIN="jns_heating_zones"
OLD_VERSION="0.3.4"
NEW_VERSION="0.3.6"
BASELINE={
    "coordinator.py":"9407ac6a9d75b772c4fe833b53cca1c7d565c61ebe40bdc5e6c8f72e609a0b74",
    "sensor.py":"f917e70602765c67fe0ed7597ea3e87cc9920b82ac773b7c2c2f2d5ce4ce9a01",
    "thermal.py":"44054f9172e3c9e2e944240b5369b49d9735d8349fb7ca2dd0a2a782d7c8a4f8",
    "__init__.py":"81160fd7e7a73cf8319d1787b8e295c464f7b1ae407db11fd4823937db901d79",
}
PROTECTED=("__init__.py","const.py","config_flow.py")
REPLACE=("coordinator.py","sensor.py","thermal.py",
         "bathroom_reference.py","bathroom_runtime.py","manifest.json")
ORIGINAL=("coordinator.py","sensor.py","thermal.py","manifest.json")
NEW_ONLY=("bathroom_reference.py","bathroom_runtime.py")
ROOT_BACKUPS=".jns_heating_backups"
STAGE_PREFIX="v036-"
MAX_BYTES=120_000

class Blocked(RuntimeError):pass

def require(cond,reason):
    if not cond:raise Blocked(reason)

def digest(b):return hashlib.sha256(b).hexdigest()

def safe(path,root):
    root=Path(root).resolve(strict=True)
    path=Path(path)
    require(path.is_relative_to(root),"path outside HA config")
    cur=root
    for part in path.relative_to(root).parts:
        cur=cur/part
        require(not cur.is_symlink(),"symlink protected path")
    return path

def read(path,root):
    safe(path,root)
    require(path.is_file(),"required HA file not present")
    data=path.read_bytes()
    require(len(data)<=MAX_BYTES,"unexpected large file")
    return data

def atomic(path,data,root,mode=None):
    safe(path,root)
    require(path.parent.is_dir(),"destination parent missing")
    require(not path.is_dir(),"destination is directory")
    current=path.stat() if path.exists() else None
    fd,temp=tempfile.mkstemp(prefix=".jns-heating-v036-",dir=path.parent)
    try:
        with os.fdopen(fd,"wb") as f:
            f.write(data); f.flush(); os.fsync(f.fileno())
        if current:
            os.chmod(temp,current.st_mode & 0o777)
            if hasattr(os,"chown"):
                os.chown(temp,current.st_uid,current.st_gid)
        else:os.chmod(temp,mode if mode is not None else 0o600)
        os.replace(temp,path)
    finally:
        if os.path.exists(temp):os.unlink(temp)

def paths(root):
    root=Path(root).resolve(strict=True)
    comp=root/"custom_components"/DOMAIN
    store=root/".storage"
    require(comp.is_dir() and store.is_dir(),"HA-General layout unavailable")
    safe(comp,root);safe(store,root)
    return root,comp,store

def require_originals(root,comp):
    for f,expected in BASELINE.items():
        require(digest(read(comp/f,root))==expected,"production fingerprint changed: "+f)
    m=json.loads(read(comp/"manifest.json",root))
    require(m.get("domain")==DOMAIN and m.get("version")==OLD_VERSION,
            "installed manifest version differs from 0.3.4")
    for extra in NEW_ONLY:
        require(not (comp/extra).exists(),"bathroom integration file already exists")
    return m

def candidate_manifest(source):
    m=json.loads(source)
    require(m.get("domain")==DOMAIN and m.get("version")==OLD_VERSION,
            "wrong candidate manifest input")
    m["version"]=NEW_VERSION
    return (json.dumps(m,indent=2,ensure_ascii=False)+"\n").encode()

def candidate_map(raw):
    require(isinstance(raw,dict) and set(raw)==set(REPLACE),"candidate file names not allowlisted")
    require(all(isinstance(k,str) and isinstance(v,bytes) and
                0<len(v)<=MAX_BYTES for k,v in raw.items()),"invalid candidate bytes")
    for name in REPLACE:
        if name.endswith(".py"):compile(raw[name],name,"exec")
    m=json.loads(raw["manifest.json"])
    require(m.get("domain")==DOMAIN and m.get("version")==NEW_VERSION,
            "candidate manifest must target exact v0.3.6")
    return raw

def snapshot(root,candidate):
    root,comp,storage=paths(root)
    require_originals(root,comp)
    raw=candidate_map(candidate)
    with_history=sorted(p for p in storage.glob("jns_heating_zone_*") if p.is_file())
    require(bool(with_history),"legacy learner storage absent")
    history={}
    for p in with_history:
        name=p.name
        require(name.startswith("jns_heating_zone_") and
                all(c.isalnum() or c in "_-" for c in name),"invalid storage name")
        blob=read(p,root)
        value=json.loads(blob).get("data",{})
        require(isinstance(value.get("samples"),list),"legacy samples unreadable")
        history[name]={"sha256":digest(blob),"samples":len(value["samples"])}
    protected={name:digest(read(comp/name,root)) for name in PROTECTED}
    expected_bytes=sum(len(read(comp/f,root)) for f in ORIGINAL)
    expected_bytes+=sum(len(raw[f]) for f in REPLACE)
    expected_bytes+=sum((storage/n).stat().st_size for n in history)
    require(shutil.disk_usage(root).free > max(10*1024*1024,3*expected_bytes),
            "insufficient storage for private backup and staging")
    return root,comp,storage,raw,history,protected

def stage(root,candidate):
    root,comp,storage,raw,history,protected=snapshot(root,candidate)
    backup=root/ROOT_BACKUPS
    safe(backup,root)
    if not backup.exists():backup.mkdir(mode=0o700)
    require(backup.is_dir(),"private backup root unavailable")
    require(backup.stat().st_mode & 0o077 == 0,"private backup root permissions unsafe")
    stage_id=STAGE_PREFIX+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"-"+uuid.uuid4().hex[:8]
    dest=backup/stage_id
    dest.mkdir(mode=0o700)
    try:
        before=dest/"original"; after=dest/"candidate"; saved=dest/"legacy_store"
        before.mkdir(mode=0o700);after.mkdir(mode=0o700);saved.mkdir(mode=0o700)
        for name,meta in history.items():
            blob=read(storage/name,root)
            require(digest(blob)==meta["sha256"],"legacy learning data changed during snapshot")
            atomic(saved/name,blob,root,mode=0o600)
        for name in ORIGINAL:
            atomic(before/name,read(comp/name,root),root,mode=0o600)
        for name in REPLACE:atomic(after/name,raw[name],root,mode=0o600)
        info={
            "stage_id":stage_id,"state":"staged","version":NEW_VERSION,
            "original":{f:digest(read(before/f,root)) for f in ORIGINAL},
            "candidate":{f:digest(read(after/f,root)) for f in REPLACE},
            "protected":protected,"history":history,
            "legacy_store_preserved":True,"core_restarted":False
        }
        atomic(dest/"state.json",(json.dumps(info,indent=2,sort_keys=True)+"\n").encode(),root,mode=0o600)
        return {"stage_id":stage_id,"state":"staged","history_count":sum(x["samples"] for x in history.values()),
            "new_integrations_active":False}
    except BaseException:
        shutil.rmtree(dest)
        raise

def get_stage(root,stage_id):
    require(stage_id.startswith(STAGE_PREFIX) and len(stage_id)==30 and
            all(c in "0123456789abcdef" for c in stage_id[-8:]),"invalid stage id")
    root,comp,storage=paths(root)
    dest=root/ROOT_BACKUPS/stage_id
    require(dest.is_dir(),"staged candidate not found")
    state=json.loads(read(dest/"state.json",root))
    require(state["stage_id"]==stage_id and state["version"]==NEW_VERSION,
            "stage metadata mismatch")
    for part in ("original","candidate","legacy_store"):
        require((dest/part).is_dir(),"private stage incomplete")
    for label,names in (("original",ORIGINAL),("candidate",REPLACE)):
        for f in names:
            require(digest(read(dest/label/f,root))==state[label][f],
                    "stage digest mismatch: "+f)
    for name,meta in state["history"].items():
        require(name.startswith("jns_heating_zone_") and
                all(char.isalnum() or char in "_-" for char in name),
                "invalid stored learning backup name")
        require(digest(read(dest/"legacy_store"/name,root))==meta["sha256"],
                "saved learning store snapshot changed")
    for f in PROTECTED:
        require(digest(read(comp/f,root))==state["protected"][f],
                "protected integration file modified: "+f)
    for f in ORIGINAL:
        require(digest(read(dest/"original"/f,root))==
                (BASELINE.get(f) or state["original"][f]),"legacy snapshot changed")
    return root,comp,storage,dest,state

def verify(root,stage_id):
    root,comp,storage,dest,state=get_stage(root,stage_id)
    expected=state["original"] if state["state"] in ("staged","rolled_back") else state["candidate"]
    names=ORIGINAL if state["state"] in ("staged","rolled_back") else REPLACE
    for f in names:
        require(digest(read(comp/f,root))==expected[f],"active file changed: "+f)
    if state["state"] in ("staged","rolled_back"):
        for f in NEW_ONLY:
            require(not (comp/f).exists(),"unapproved new module installed")
    for name,record in state["history"].items():
        require((storage/name).is_file(),"legacy learning store absent")
        samples=json.loads(read(storage/name,root)).get("data",{}).get("samples")
        require(isinstance(samples,list),"legacy learning history unreadable")
        # Store grows while Core runs. Never restore saved history over live data.
    return {"stage_id":stage_id,"state":state["state"],
            "active_files_sha256_verified":True,"core_restarted":False,
            "existing_history_preserved":True}

def apply(root,stage_id,approved=False):
    require(approved,"a separate local root-owned JNS permit is required")
    require(verify(root,stage_id)["state"]=="staged","stage not ready")
    root,comp,storage,dest,state=get_stage(root,stage_id)
    changed=[]
    try:
        for f in REPLACE:
            atomic(comp/f,read(dest/"candidate"/f,root),root,mode=0o644)
            changed.append(f)
        state["state"]="applied_pending_core_restart"
        atomic(dest/"state.json",(json.dumps(state,indent=2,sort_keys=True)+"\n").encode(),root)
        verify(root,stage_id)
        return {"state":state["state"],"restart_required":True,
                "successful_activation":False,"stage_id":stage_id}
    except BaseException:
        for f in reversed(changed):
            if f in ORIGINAL:atomic(comp/f,read(dest/"original"/f,root),root)
            else:(comp/f).unlink(missing_ok=True)
        raise

def rollback(root,stage_id,approved=False):
    require(approved,"a separate local root-owned JNS permit is required")
    root,comp,storage,dest,state=get_stage(root,stage_id)
    require(state["state"]=="applied_pending_core_restart","rollback state invalid")
    for f in REPLACE:
        require(digest(read(comp/f,root))==state["candidate"][f],
                "refuse rollback over later source changes: "+f)
    for f in ORIGINAL:atomic(comp/f,read(dest/"original"/f,root),root)
    for f in NEW_ONLY:(comp/f).unlink(missing_ok=True)
    state["state"]="rolled_back"
    atomic(dest/"state.json",(json.dumps(state,indent=2,sort_keys=True)+"\n").encode(),root)
    return {"state":"rolled_back","restart_required":True,
            "legacy_store_preserved":True}

def cli():
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("preflight","stage","verify","apply","rollback"))
    p.add_argument("--root",default="/config")
    p.add_argument("--stage-id")
    p.add_argument("--candidate")
    args=p.parse_args()
    try:
        if args.action in ("stage","preflight"):
            require(args.candidate is not None,"candidate JSON bundle required")
            bundle=json.loads(Path(args.candidate).read_text())
            import base64
            raw={k:base64.b64decode(v,validate=True) for k,v in bundle.items()}
            if args.action=="stage":out=stage(args.root,raw)
            else:
                root,comp,storage,_,history,_=snapshot(args.root,raw)
                out={"preflight":True,"history_count":sum(h["samples"] for h in history.values())}
        else:
            require(args.stage_id is not None,"stage identifier required")
            if args.action=="verify":out=verify(args.root,args.stage_id)
            else:
                # Production entry points are intentionally NOT exposed through
                # this CLI. Root-owned capability must call apply/rollback after
                # permit verification. A GitHub runner cannot activate by flag.
                raise Blocked("activation requires separate root-owned gateway capability")
        print("JNS_BATHROOM_V036",json.dumps(out,sort_keys=True))
    except (Blocked,ValueError,KeyError,OSError,TypeError,SyntaxError) as exc:
        print("JNS_BATHROOM_V036_BLOCKED",type(exc).__name__,str(exc)[:180])
        raise SystemExit(2)

if __name__=="__main__":
    cli()
