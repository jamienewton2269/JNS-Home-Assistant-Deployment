#!/usr/bin/env python3
"""Read-only VM905 heating runtime attestation, executed *inside* HA Core.

Reuses the pre-existing root-private JNS Steward credential; never creates
tokens, prints them, exports them, writes to Home Assistant or calls services.
Calls ONLY fixed local GET endpoints for essential heating entities.
"""
from __future__ import annotations
import json
import math
import os
from pathlib import Path
import stat
import sys
import urllib.error
import urllib.request

CRED_DIR=Path("/config/.jns-steward")
TOKEN=CRED_DIR/"ha_general_api.token"
API="http://127.0.0.1/api"
CLIMATE="climate.thermostat_thermostat"
INDOOR="sensor.thermostat_thermostat_indoor_temperature"
HEATING_CALL="binary_sensor.lyric_home_heating_heating_call"
LEARNER="sensor.lyric_home_heating_thermal_learning"
ENTITIES=(CLIMATE,INDOOR,HEATING_CALL,LEARNER)

class Unavailable(RuntimeError): pass

def private_token():
    if os.geteuid()!=0 or CRED_DIR.is_symlink() or not CRED_DIR.is_dir():
        raise Unavailable("Steward credential directory unavailable")
    if CRED_DIR.stat().st_uid!=0 or stat.S_IMODE(CRED_DIR.stat().st_mode)!=0o700:
        raise Unavailable("Steward credential directory permissions incorrect")
    if TOKEN.is_symlink() or not TOKEN.is_file():
        raise Unavailable("Steward local API credential unavailable")
    info=TOKEN.stat()
    if info.st_uid!=0 or stat.S_IMODE(info.st_mode)!=0o600 or not 64<=info.st_size<=1024:
        raise Unavailable("Steward API credential permissions or size invalid")
    value=TOKEN.read_text(encoding="utf-8").strip()
    if not 64<=len(value)<=1024 or any(ch.isspace() for ch in value):
        raise Unavailable("Steward API credential format invalid")
    return value

def http_get(token,entity):
    if entity not in ENTITIES:
        raise Unavailable("unapproved API entity query")
    request=urllib.request.Request(API+"/states/"+entity,
        method="GET",headers={"Authorization":"Bearer "+token,
                              "Accept":"application/json"})
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request,timeout=8) as response:
            if response.status!=200:
                raise Unavailable("Home Assistant API did not serve entity")
            return json.loads(response.read(16000))
    except (urllib.error.HTTPError,urllib.error.URLError,TimeoutError,
            ValueError,json.JSONDecodeError):
        raise Unavailable("Home Assistant entity API unavailable") from None

def assess(record):
    if set(record)!=set(ENTITIES):
        return {"ready":False,"climate_ok":False,"indoor_ok":False,
                "heating_call_ok":False,"learner_exists":False}
    def actual(e):
        obj=record.get(e)
        if not isinstance(obj,dict) or obj.get("entity_id")!=e:
            return None
        return str(obj.get("state","")).strip()
    climate=actual(CLIMATE)
    interior=actual(INDOOR)
    call=actual(HEATING_CALL)
    model=actual(LEARNER)
    climate_ok=climate is not None and climate not in ("","unknown","unavailable","none")
    try:
        indoor_ok=interior is not None and math.isfinite(float(interior))
    except (ValueError,TypeError):
        indoor_ok=False
    call_ok=call in ("on","off")
    # Learning might correctly be not ready, even though its entity exists.
    learner_exists=model is not None
    return {"ready":climate_ok and indoor_ok and call_ok and learner_exists,
            "climate_ok":climate_ok,"indoor_ok":indoor_ok,
            "heating_call_ok":call_ok,"learner_exists":learner_exists}

def main():
    token=private_token()
    states={name:http_get(token,name) for name in ENTITIES}
    result=assess(states)
    print("JNS_HEATING_RUNTIME",json.dumps(result,sort_keys=True),flush=True)
    if not result["ready"]:
        raise SystemExit(2)

if __name__=="__main__":
    try:
        main()
    except (Unavailable,OSError) as exc:
        # Output contains NO token, raw state, room temperature or setpoint.
        print("JNS_HEATING_RUNTIME_BLOCKED",type(exc).__name__,str(exc)[:130],
              file=sys.stderr)
        sys.exit(2)
