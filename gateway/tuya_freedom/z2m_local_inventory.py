#!/usr/bin/env python3
"""Check the existing Zigbee2MQTT CT214 coordinator inventory without pair/restart.

Return only anonymous aggregate device counts to public GitHub Actions.
Never read Z2M credentials or dump device IEEE addresses.
"""
import json,sys
sys.path.insert(0,"gateway/arrival_lighting")
from readiness_probe import ssh_host
PY = r'''
import collections,json,pathlib
paths=[
 pathlib.Path("/opt/zigbee2mqtt/data/database.db"),
 pathlib.Path("/var/lib/zigbee2mqtt/data/database.db"),
 pathlib.Path("/app/data/database.db"),
 pathlib.Path("/data/database.db"),
]
found=next((p for p in paths if p.is_file()),None)
if not found:
    print(json.dumps({"status":"database_not_found"}));raise SystemExit(0)
counts=collections.Counter()
models=collections.Counter()
for line in found.open(errors="replace"):
    try:item=json.loads(line)
    except ValueError:continue
    if not isinstance(item,dict):continue
    typ=str(item.get("type") or "Unknown")
    counts["total"]+=1
    counts["type_"+typ]+=1
    manufacturer=str(item.get("manufacturerName") or "")
    model=str(item.get("modelID") or "")
    if "tuya" in manufacturer.lower() or model.startswith("TS") or model.startswith("TY"):
        counts["probable_tuya"]+=1
    if typ=="EndDevice":counts["battery_or_sleepy_end_devices"]+=1
print(json.dumps({"status":"read_only_ok","counts":dict(counts)}))
'''
def main():
    if "running" not in ssh_host("nodeb",["pct","status","214"]):
        raise RuntimeError("ct214_not_running")
    # Execute inside CT214: stdout contains aggregate counts only.
    result=ssh_host("nodeb",["pct","exec","214","--","python3","-c",PY])
    return json.loads(result.strip())
if __name__=="__main__":
    try:print("JNS_TUYA_Z2M_LOCAL_INVENTORY",json.dumps(main(),sort_keys=True),flush=True)
    except Exception as e:
        print("JNS_TUYA_Z2M_LOCAL_INVENTORY_BLOCKED",type(e).__name__,flush=True)
        raise SystemExit(1)
