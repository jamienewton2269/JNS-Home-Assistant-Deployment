#!/usr/bin/env python3
"""Root-owned VM905 JNS Heating Zones v0.3.5 release controller.

NOT A GITHUB RUNNER SCRIPT. Install as root:root mode 0700 on Node B along
with its companion transaction.py in /usr/local/libexec/jns-heating/.
Requires a *local* root-owned, short-lived approval and HA administrator
token. Never log, export, or copy credentials into GitHub.

Scope: one VM, one HA config entry, one stage, no thermostat commands,
no HA Core restart. Only integration reload using Home Assistant's
administrator-authenticated REST endpoint. Rollback restores only the two
component source files and reloads the original entry; learning store is
NEVER rolled back or rewritten.
"""
from __future__ import annotations
from datetime import datetime,timezone,timedelta
import base64
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request
import urllib.error

VM="905"
ENTRY="01M3VTS63FBE0BWHQ5WDGNBH5E"
STAGE="v035-20261024T162546Z-43b0f6ec"
SHA="43b0f6ec0229d15dc137bbf3c52cd41b4bb125072fbcc49202e744ba8a19bc6c"
TOKEN_FILE=Path("/etc/jns/ha-general-api.token")
APPROVAL_FILE=Path("/etc/jns/heating-v035-approval.json")
GUEST_PROGRAM=Path("/usr/local/libexec/jns-heating/transaction.py")
LOCK_FILE=Path("/etc/jns/heating-v035.lock")
BASE="http://ha-general.home.arpa:80"
REQUIRED=("climate.thermostat_thermostat",
          "binary_sensor.lyric_home_heating_heating_call",
          "sensor.thermostat_thermostat_indoor_temperature",
          "sensor.lyric_home_heating_thermal_learning")

class Blocked(RuntimeError):
    pass

def require(test,message):
    if not test:raise Blocked(message)

def secure_file(path):
    require(path.is_file() and not path.is_symlink(),"local authority file missing")
    s=path.stat()
    require(s.st_uid==0 and s.st_mode&0o077==0,"unsafe authority file ownership/permissions")
    return path.read_bytes()

def approval():
    require(os.geteuid()==0,"root privileges required")
    record=json.loads(secure_file(APPROVAL_FILE))
    require(set(record)=={"stage_id","candidate_sha256","intent","expires_utc"},
            "invalid approval schema")
    require(record["stage_id"]==STAGE and record["candidate_sha256"]==SHA,
            "release target mismatch")
    require(record["intent"]=="promote_v035","wrong approval intent")
    expires=datetime.fromisoformat(record["expires_utc"].replace("Z","+00:00"))
    require(expires.tzinfo is not None,"approval must be timezone-aware")
    seconds=(expires-datetime.now(timezone.utc)).total_seconds()
    require(0<seconds<=30*60,"approval expired or lifetime exceeds 30 minutes")
    return record

def auth_token():
    content=secure_file(TOKEN_FILE).decode().strip()
    require(len(content)>=40 and "\n" not in content,"invalid local token file")
    return content

def api(method,path,payload=None,timeout=12):
    require(path.startswith("/api/") and "\n" not in path,"invalid HA API endpoint")
    token=auth_token()
    headers={"Authorization":"Bearer "+token,"Content-Type":"application/json"}
    blob=json.dumps(payload).encode() if payload is not None else None
    req=urllib.request.Request(BASE+path,headers=headers,method=method,data=blob)
    try:
        with urllib.request.urlopen(req,timeout=timeout) as response:
            raw=response.read(256*1024)
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raise Blocked("HA API status "+str(exc.code)+" for "+method+" "+path) from None
    except Exception as exc:
        raise Blocked("HA API unavailable: "+type(exc).__name__) from None

def live_snapshot():
    core=api("GET","/api/core/state")
    require(core.get("state")=="RUNNING","Home Assistant Core not running")
    recorder=core.get("recorder_state") or {}
    require(recorder.get("migration_in_progress") is not True,"recorder migration active")
    states={}
    for entity in REQUIRED:
        result=api("GET","/api/states/"+entity)
        require(result.get("entity_id")==entity,"live entity mismatch")
        require(result.get("state") not in ("unknown","unavailable",None),
                "live entity unavailable: "+entity)
        states[entity]=result
    return states

def idle(states):
    call=states["binary_sensor.lyric_home_heating_heating_call"]
    require(call.get("state")=="off","heating call active: block integration reload")
    climate=states["climate.thermostat_thermostat"]
    action=(climate.get("attributes") or {}).get("hvac_action")
    require(action not in ("heating","cooling"),"thermostat actively controlling heat")
    indoor=states["sensor.thermostat_thermostat_indoor_temperature"]["state"]
    try:require(-10<float(indoor)<45,"temperature outside valid range")
    except ValueError:raise Blocked("temperature not numeric") from None

def qm(args,timeout=90):
    p=subprocess.run(["qm",*args],capture_output=True,text=True,timeout=20,check=True)
    r=json.loads(p.stdout)
    if r.get("exited"):return r
    pid=r.get("pid")
    require(isinstance(pid,int),"QGA did not return an execution PID")
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        time.sleep(1)
        p=subprocess.run(["qm","guest","exec-status",VM,str(pid)],
                         capture_output=True,text=True,timeout=15,check=True)
        r=json.loads(p.stdout)
        if r.get("exited"):return r
    raise Blocked("QGA operation status uncertain; manual inspection required")

def guest_txn(action):
    require(action in ("verify","commit","rollback"),"disallowed transaction action")
    script=secure_file(GUEST_PROGRAM)
    require(script.startswith(b"#!/usr/bin/env python3"),"unexpected guest helper")
    args=["transaction.py",action,"--root","/config","--stage-id",STAGE]
    if action!="verify":args.append("--gateway-authorised")
    command=("import base64,sys\n"
             "sys.argv="+repr(args)+"\n"
             "exec(compile(base64.b64decode("+repr(base64.b64encode(script).decode())+
             "),'<jns-approved-heating-transaction>','exec'))\n")
    encoded=base64.b64encode(command.encode()).decode()
    expression="exec(__import__('base64').b64decode('"+encoded+"'))"
    result=qm(["guest","exec",VM,"--","docker","exec","homeassistant",
               "python3","-c",expression])
    output=(result.get("out-data") or "").strip()
    require(result.get("exitcode")==0 and output.startswith("JNS_HEATING_GUARDED "),
            "guest transaction blocked: "+action)
    return json.loads(output.partition(" ")[2])

def reload_entry():
    result=api("POST","/api/config/config_entries/entry/"+ENTRY+"/reload",{},timeout=55)
    require(result.get("require_restart") is False,
            "config entry requires restart or reload rejected")

def loaded(*,candidate=False):
    deadline=time.monotonic()+115
    while time.monotonic()<deadline:
        try:
            states=live_snapshot()
            sensor=states["sensor.lyric_home_heating_thermal_learning"]
            require(sensor.get("state") not in ("unknown","unavailable"),
                    "thermal learner unavailable")
            if candidate:
                require("valid_windows" in (sensor.get("attributes") or {}),
                        "candidate learner status has not reached live entity")
            return states
        except Blocked:
            time.sleep(5)
    raise Blocked("HA heating entities/expected learner did not recover")

def is_candidate_live(states):
    sensor=states["sensor.lyric_home_heating_thermal_learning"]
    attrs=sensor.get("attributes") or {}
    # Version 0.3.5 introduces this attribute; its presence is evidence
    # that the running coordinator is using the newly loaded learner.
    require("valid_windows" in attrs,"new learner diagnostics are not live")
    return {"valid_windows":attrs.get("valid_windows"),
            "ready":attrs.get("ready"),
            "state":sensor.get("state")}

def _run_body():
    require(len(sys.argv)==2 and sys.argv[1] in ("--preflight","--promote"),
            "unknown requested operation")
    require(os.geteuid()==0,"root privileges required")
    approved=approval()
    before=live_snapshot()
    idle(before)
    phase=guest_txn("verify")
    require(phase.get("state")=="staged" and phase.get("backups_integrity_verified"),
            "private v0.3.5 stage not verified")
    if sys.argv[1]=="--preflight":
        print("JNS_HEATING_SAFE_TO_PROMOTE "+json.dumps({
            "state":"ready","guest":"905","stage":STAGE,
            "current_call":"off","runtime":"RUNNING","restart_required":False}))
        return
    # Enforce fresh idle state, then consume the root-owned approval once.
    idle(live_snapshot())
    consume_approval()
    try:
        state=guest_txn("commit")
        require(state.get("state")=="applied_pending_runtime_verification",
                "transaction did not apply expected candidate")
        reload_entry()
        after=loaded(candidate=True)
        info=is_candidate_live(after)
        # Check file post-state after authenticated reload.
        verified=guest_txn("verify")
        require(verified.get("state")=="applied_pending_runtime_verification",
                "post-reload component fingerprint mismatch")
        print("JNS_HEATING_V035_LIVE "+json.dumps({
             "stage":STAGE,"version":"0.3.5","learner":info,
             "global_core_restart":False,"store_preserved":True}))
    except BaseException:
        try:
            current=guest_txn("verify")
            if current.get("state")=="applied_pending_runtime_verification":
                guest_txn("rollback")
                reload_entry()
                loaded()
                print("JNS_HEATING_ROLLBACK_CONFIRMED")
            elif current.get("state")=="staged":
                print("JNS_HEATING_NO_PRODUCTION_CHANGE")
            else:
                raise Blocked("unexpected release state after failed promotion")
        except BaseException:
            print("JNS_HEATING_CRITICAL_ROLLBACK_NEEDS_OPERATOR",file=sys.stderr)
        raise

def consume_approval():
    # Only a Node B root process within the release lock may consume this file.
    # The previous approval() verified stage, digest, owner, time and intent.
    secure_file(APPROVAL_FILE)
    APPROVAL_FILE.unlink()


def run():
    require(os.geteuid()==0,"root privileges required")
    # A second invocation must never interleave file writes and HA reloads.
    with LOCK_FILE.open("a+") as handle:
        try:
            fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            raise Blocked("another JNS heating release is active") from None
        return _run_body()


if __name__=="__main__":
    try:run()
    except BaseException as exc:
        print("JNS_HEATING_RELEASE_BLOCKED",type(exc).__name__,
              str(exc)[:200],file=sys.stderr)
        raise SystemExit(2)
