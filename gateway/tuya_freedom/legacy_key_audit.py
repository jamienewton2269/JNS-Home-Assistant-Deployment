#!/usr/bin/env python3
"""Check whether legacy VM900 already possesses the seven missing local keys.

Performs read-only registry inspection over existing trusted QGA/SSH.
No Tuya cloud use. Neither the local keys nor device IDs are printed,
put in GitHub logs, or copied from their original servers.
"""
import base64,json,sys,time
sys.path.insert(0,"gateway/arrival_lighting")
from readiness_probe import ssh_host

TARGET=r'''
import json,pathlib
base=pathlib.Path("/config")
f=base/".jns_tuya_freedom/latest-live.json"
live=json.loads(f.read_text())
print(json.dumps({"physical_missing_ids":[str(x.get("native_device_id")).strip().lower() for x in live.get("physical_devices",[]) if not x.get("local_configured")],
                  "count":sum(not x.get("local_configured") for x in live.get("physical_devices",[]))}))
'''
LEGACY=r'''
import json,pathlib
root=pathlib.Path("/config/.storage")
cfg=json.loads((root/"core.config_entries").read_text())["data"]["entries"]
out=[]
for e in cfg:
    if e.get("domain") not in ("tuya_local","localtuya"):continue
    data=e.get("data") or {}
    opts=e.get("options") or {}
    ids=[]
    for field in ("device_id","id","gwId"):
        for v in (data.get(field),opts.get(field)):
            if isinstance(v,str) and len(v.strip())>=12:ids.append(v.strip().lower())
    # Do not return local keys; return only booleans.
    has_key=any(bool(obj.get(k)) for obj in (data,opts) for k in ("local_key","localKey","device_key"))
    out.append({"ids":ids,"local_key_present":has_key})
print(json.dumps({"local_configured_ids":out,"local_entry_count":len(out)}))
'''
def guest(node,vm,source,timeout=100):
    arg="exec(__import__('base64').b64decode('"+base64.b64encode(source.encode()).decode()+"'))"
    raw=json.loads(ssh_host(node,["qm","guest","exec",str(vm),"--","docker","exec","homeassistant","python3","-c",arg]))
    pid=raw.get("pid");expiry=time.monotonic()+timeout
    while not raw.get("exited"):
        if not isinstance(pid,int) or time.monotonic()>expiry:raise RuntimeError("qga_guest_unavailable")
        time.sleep(2)
        raw=json.loads(ssh_host(node,["qm","guest","exec-status",str(vm),str(pid)]))
    if raw.get("exitcode")!=0:raise RuntimeError("guest_failed")
    return json.loads(raw.get("out-data",""))
def main():
    a=guest("nodeb",905,TARGET)
    missing={str(v).lower() for v in a["physical_missing_ids"]}
    if len(missing)!=7:raise RuntimeError("expected_seven_migration_targets")
    try:
        if "running" not in ssh_host("nodea",["qm","status","900"]):
            return {"status":"vm900_not_running","legacy_keys_matched_to_seven":None}
        b=guest("nodea",900,LEGACY)
    except Exception:
        return {"status":"vm900_local_registry_unavailable","legacy_keys_matched_to_seven":None}
    withkeys={v for e in b.get("local_configured_ids",[]) if e.get("local_key_present") for v in e.get("ids",[])}
    matched=missing & withkeys
    return {"status":"read_only_completed","legacy_local_entries":b.get("local_entry_count",0),
            "missing_seven_found_in_legacy_local_keys":len(matched),
            "missing_seven_without_legacy_keys":len(missing-matched),
            "credentials_exported":False}
if __name__=="__main__":
    try:print("JNS_TUYA_LEGACY_KEYS_AUDIT",json.dumps(main(),sort_keys=True),flush=True)
    except Exception as exc:
        print("JNS_TUYA_LEGACY_KEYS_BLOCKED",type(exc).__name__,flush=True)
        raise SystemExit(1)
