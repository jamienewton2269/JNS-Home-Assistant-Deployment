#!/usr/bin/env python3
"""Read-only VM905 heating runtime entity-ID inventory.

Prints IDs and an availability BOOLEAN only; never state values, setpoints,
sensor readings, credentials, addresses, or unrelated entity names.
"""
import base64,json,sys,time
sys.path.insert(0,"gateway/arrival_lighting")
from readiness_probe import ssh_host

def qga(argv):
    r=json.loads(ssh_host("nodeb",["qm","guest","exec","905","--",*argv]))
    end=time.monotonic()+85
    while not r.get("exited"):
        if not isinstance(r.get("pid"),int) or time.monotonic()>end:
            raise RuntimeError("read-only VM905 guest command timed out")
        time.sleep(1)
        r=json.loads(ssh_host("nodeb",["qm","guest","exec-status","905",str(r["pid"])]))
    if r.get("exitcode")!=0:
        raise RuntimeError("read-only VM905 guest command failed")
    return (r.get("out-data") or "").strip()

CORE=r"""
import json,pathlib
es=json.loads((pathlib.Path('/config/.storage/core.entity_registry')).read_text())['data']['entities']
selected=sorted(set(e.get('entity_id','') for e in es if
  e.get('entity_id','').startswith('climate.') or
  e.get('entity_id','').startswith('sensor.thermostat_') or
  e.get('entity_id','').startswith('binary_sensor.lyric_home_heating_heating_call')))
print(json.dumps({"registered_ids":selected[:35],"count":len(selected)},sort_keys=True))
"""
core_script="exec(__import__('base64').b64decode('"+base64.b64encode(CORE.encode()).decode()+"'))"
r1=json.loads(qga(["docker","exec","homeassistant","python3","-c",core_script]))
print("JNS_HEATING_ENTITY_REGISTRY_IDS",json.dumps(r1,sort_keys=True),flush=True)
SH=r"""
test -n "$SUPERVISOR_TOKEN" || exit 2
raw="$(curl -fsS -m 12 -H "Authorization: Bearer $SUPERVISOR_TOKEN" \
  http://supervisor/core/api/states 2>/dev/null)" || exit 2
printf '%s' "$raw" | jq -c '
 [.[]
 | select((.entity_id | startswith("climate.")) or
          (.entity_id | startswith("sensor.thermostat_")) or
          (.entity_id == "binary_sensor.lyric_home_heating_heating_call"))
 | {"entity_id":.entity_id,
    "available":(.state != "unknown" and .state != "unavailable" and .state != null)}
 ] | sort_by(.entity_id) | .[:35]' 
"""
try:
    r2=json.loads(qga(["docker","exec","app_core_ssh","sh","-c",SH]))
except Exception as exc:
    print("JNS_HEATING_LIVE_ENTITY_LIST_BLOCKED",type(exc).__name__,flush=True)
else:
    print("JNS_HEATING_ACTIVE_ENTITY_IDS",json.dumps(r2,sort_keys=True),flush=True)
