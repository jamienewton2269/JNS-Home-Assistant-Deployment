#!/usr/bin/env python3
"""Use installed Tuya Local discovery capability to find current LAN addresses.

Passive, local-only Tuya UDP discovery, not cloud API and no control commands.
Finds only the *two* unavailable local devices. Saves all target IDs and IPs
inside VM905 with private file permissions; GitHub sees only counts.
"""
import base64,json,sys,time
sys.path.insert(0,"gateway/arrival_lighting")
from readiness_probe import ssh_host
GUEST=r'''
import collections,datetime,json,os,pathlib
import tinytuya
root=pathlib.Path("/config")
home=root/".jns_tuya_freedom"
live=json.loads((home/"latest-live.json").read_text())
now=datetime.datetime.now(datetime.timezone.utc)
if not 0<=(now-datetime.datetime.fromisoformat(live["generated_utc"])).total_seconds()<=900:
    raise RuntimeError("observer_report_stale")
entries=json.loads((root/".storage/core.config_entries").read_text())["data"]["entries"]
local={str(x.get("data",{}).get("device_id","")).strip().lower():x
       for x in entries if x.get("domain")=="tuya_local"}
candidate=[]
for row in live["physical_devices"]:
    if row.get("local_configured") and int(row.get("available_local_entities") or 0)==0:
        native=str(row.get("native_device_id","")).strip().lower()
        cfg=local.get(native)
        if cfg and isinstance(cfg.get("data",{}).get("host"),str):
            candidate.append((native,cfg["data"]["host"]))
if len(candidate)>2:raise RuntimeError("too_many_unavailable_devices")
counts=collections.Counter()
rows=[]
for native,old_host in candidate:
    counts["candidates"]+=1
    try:
        device=tinytuya.find_device(dev_id=native)
        if not isinstance(device,dict):device={}
        found_id=str(device.get("gwId") or device.get("id") or "").strip().lower()
        ip=str(device.get("ip") or "").strip()
        # The caller looks up an exact native device ID; further identity
        # matching is required before any setting is changed.
        if ip:
            counts["discovered_lan_address"]+=1
            if ip!=old_host:counts["discovered_address_differs"]+=1
            else:counts["discovered_address_matches"]+=1
        else:
            counts["not_discovered"]+=1
        rows.append({"native_id":native,"configured_host":old_host,
                     "discovered_address":ip or None,
                     "scanner_returned_id_matches":found_id==native if found_id else None,
                     "device_type":device.get("version"),
                     "proposal_approved":False})
    except Exception as e:
        counts["scanner_exception"]+=1
        rows.append({"native_id":native,"configured_host":old_host,
                     "discovered_address":None,
                     "scanner_failure_class":type(e).__name__,
                     "proposal_approved":False})
output=home/("udp-discovery-"+now.strftime("%Y%m%dT%H%M%SZ")+".json")
fd=os.open(str(output),os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
with os.fdopen(fd,"w") as f:
    json.dump({"schema":1,"utc":now.isoformat(),
               "note":"Read-only discovery; verify device identity and DNS before reconfiguration.",
               "devices":rows,"aggregate":dict(counts)},f,indent=2,sort_keys=True)
    f.write("\n")
print(json.dumps({"status":"READ_ONLY_DISCOVERY_FINISHED",
                  "counts":dict(counts),"onboarding_changes":0,
                  "private_report_saved":True},sort_keys=True))
'''
def main():
    if "running" not in ssh_host("nodeb",["qm","status","905"]):
        raise RuntimeError("vm905_offline")
    source="exec(__import__('base64').b64decode('"+base64.b64encode(GUEST.encode()).decode()+"'))"
    r=json.loads(ssh_host("nodeb",["qm","guest","exec","905","--","docker","exec","homeassistant","python3","-c",source]))
    pid=r.get("pid")
    deadline=time.monotonic()+115
    while not r.get("exited"):
        if time.monotonic()>deadline or not isinstance(pid,int):
            raise RuntimeError("guest_udp_discovery_timeout")
        time.sleep(2)
        r=json.loads(ssh_host("nodeb",["qm","guest","exec-status","905",str(pid)]))
    if r.get("exitcode")!=0:
        raise RuntimeError("local_discovery_error")
    return json.loads(r.get("out-data",""))
if __name__=="__main__":
    try:print("JNS_TUYA_TWO_DEVICE_DISCOVERY",json.dumps(main(),sort_keys=True),flush=True)
    except Exception as e:
        print("JNS_TUYA_TWO_DEVICE_DISCOVERY_BLOCKED",type(e).__name__,str(e)[:80],flush=True)
        raise SystemExit(1)
