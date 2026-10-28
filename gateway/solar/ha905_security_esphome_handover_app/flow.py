#!/usr/bin/env python3
"""Single-use native Home Assistant ESPHome flow, source fenced by Node C.

This app has administrator-equivalent Core API scope: the trusted gateway must
verify VM906 is stopped with Node A local recovery active BEFORE starting it.
The app never toggles outputs/automations; it only enrols a native ESPHome
integration via official config flow. Sensitive host/key/password never logged.
"""
import json
import os
import pathlib
import re
import sys
import time
import urllib.error
import urllib.request

BASE = "http://supervisor/core/api/"
FLOW_PATH = "config/config_entries/flow"
SECRET = pathlib.Path("/share/jns-security-handover-20261028/enrolment.json")
MARKER = pathlib.Path("/data/jns-one-flow-started-20261028")
METHODS = frozenset(("GET", "POST", "DELETE"))
# Config-entry flows in HA Core 2026.9.4 use 26-character Crockford ULIDs,
# whereas legacy generic flows used 32-character hexadecimal UUIDs.
# Accept only these two canonical, path-safe identifiers, not arbitrary strings.
FLOW_ID_RE = re.compile(r"(?:[0-9A-HJKMNP-TV-Z]{26}|[0-9a-fA-F]{32})")

def note(k,v):
    print("JNS_ESP_HANDOVER_" + k + "=" + str(v),flush=True)

def stop(reason):
    note("BLOCKED",reason)
    raise SystemExit(71)

def request(method,path,token,payload=None,opener=urllib.request.urlopen):
    if method not in METHODS:
        raise ValueError("unapproved_method")
    if not (path == FLOW_PATH or (
            path.startswith(FLOW_PATH + "/") and
            FLOW_ID_RE.fullmatch(path[len(FLOW_PATH) + 1:]))):
        raise ValueError("unapproved_endpoint")
    if not token:
        raise ValueError("missing_supervisor_token")
    headers = {"Authorization":"Bearer " + token,"Content-Type":"application/json"}
    data = None if payload is None else json.dumps(payload,separators=(",",":")).encode()
    req = urllib.request.Request(BASE + path,data=data,headers=headers,method=method)
    try:
        with opener(req,timeout=23) as response:
            if response.status not in (200,201):
                raise ValueError("unexpected_http_status")
            result = response.read(100000)
            if not result:
                return {}
            return json.loads(result)
    except urllib.error.HTTPError as exc:
        # Status and fixed phase ONLY. Never display URL, response, credentials,
        # device address, form data, or HTTP error message.
        phase = ("start" if method == "POST" and path == FLOW_PATH else
                 "step" if method == "POST" else
                 "poll" if method == "GET" else "cleanup")
        note("HTTP_PHASE", phase)
        note("HTTP_STATUS", str(exc.code) if exc.code in
             (400, 401, 403, 404, 405, 409, 422, 429, 500, 502, 503, 504) else "other")
        raise

def safe_stage():
    if SECRET.is_symlink() or not SECRET.is_file():
        stop("private_enrolment_stage_missing")
    if SECRET.stat().st_size > 16000:
        stop("oversize_stage")
    data = json.loads(SECRET.read_text())
    if data.get("source_vm") != 906 or data.get("target_vm") != 905:
        stop("source_target_identity")
    if data.get("single_controller_gate") != "vm906_stopped_recovery_armed":
        stop("exclusive_owner_confirmation")
    record=data.get("esphome",{})
    if not isinstance(record,dict):
        stop("invalid_staged_record")
    host=record.get("host")
    port=record.get("port",6053)
    key=record.get("noise_psk")
    password=record.get("password","")
    if not (isinstance(host,str) and 1<=len(host)<=255
            and isinstance(port,int) and 1<=port<=65535
            and isinstance(key,str) and len(key)>=40
            and isinstance(password,str)):
        stop("invalid_esp_connection_shape")
    return {"host":host,"port":port,"noise_psk":key,"password":password}

def run_flow(credentials,token,api=request):
    flow_id=None
    created=False
    steps=[]
    try:
        response=api("POST",FLOW_PATH,token,{"handler":"esphome"})
        for _ in range(9):
            if not isinstance(response,dict):
                stop("invalid_flow_response")
            stage=response.get("type")
            step=response.get("step_id")
            if stage=="create_entry":
                created=True
                note("ENTRY_CREATED", "yes")
                return True
            if stage=="abort":
                note("ABORT_REASON",str(response.get("reason","unknown"))[:75])
                return False
            if stage=="progress":
                if not flow_id:stop("missing_flow_id")
                time.sleep(2)
                response=api("GET",FLOW_PATH+"/"+flow_id,token)
                continue
            if stage!="form":
                stop("unsupported_flow_step")
            flow_id=response.get("flow_id",flow_id)
            if not isinstance(flow_id,str) or not FLOW_ID_RE.fullmatch(flow_id):
                stop("invalid_flow_identifier")
            errors=response.get("errors") or {}
            if errors:
                note("FLOW_ERROR_CODE",",".join(str(x)[:40] for x in errors.values())[:120])
                return False
            if step in steps:
                stop("repeated_flow_step")
            steps.append(step)
            if step=="user":
                form={"host":credentials["host"],"port":credentials["port"]}
            elif step=="encryption_key":
                form={"noise_psk":credentials["noise_psk"]}
            elif step=="authenticate":
                if not credentials["password"]:
                    stop("legacy_password_unavailable")
                form={"password":credentials["password"]}
            else:
                stop("unexpected_step")
            note("FLOW_STEP",step)
            response=api("POST",FLOW_PATH+"/"+flow_id,token,form)
        stop("flow_step_limit")
    finally:
        if flow_id and not created:
            try:api("DELETE",FLOW_PATH+"/"+flow_id,token)
            except Exception:pass

def main():
    if MARKER.exists() or MARKER.is_symlink():
        stop("one_shot_already_attempted")
    token=os.environ.get("SUPERVISOR_TOKEN","")
    if not token:
        stop("supervisor_token_absent")
    credentials=safe_stage()
    with MARKER.open("x") as f:
        f.write("one authorised ESPHome enrolment attempt\n")
        f.flush()
        os.fsync(f.fileno())
    try:
        success=run_flow(credentials,token)
    except (ValueError,KeyError,TimeoutError,urllib.error.URLError,
            urllib.error.HTTPError,json.JSONDecodeError) as ex:
        # Only class names, never contents of auth or error responses.
        note("FLOW_EXCEPTION_CLASS",type(ex).__name__)
        return 2
    if not success:return 3
    note("NATIVE_CONFIG_FLOW_COMPLETE","yes")
    return 0

if __name__=="__main__":
    sys.exit(main())
