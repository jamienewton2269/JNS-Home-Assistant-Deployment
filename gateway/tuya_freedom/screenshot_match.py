#!/usr/bin/env python3
"""Identify, without divulging IDs or keys, which HA-General Tuya Local bulb
matches the trusted device-ID LAN discovery at 10.10.101.185.
"""
import base64,json,sys,time
sys.path.insert(0,"gateway/arrival_lighting")
from readiness_probe import ssh_host
GUEST=r'''
import json,pathlib,socket,datetime
root=pathlib.Path("/config")
private=root/".jns_tuya_freedom"
configs=json.loads((root/".storage/core.config_entries").read_text())["data"]["entries"]
local={str(e.get("data",{}).get("device_id") or "").strip().lower():e
 for e in configs if e.get("domain")=="tuya_local"}
files=sorted(private.glob("udp-discovery-*.json"))
if not files:raise RuntimeError("discovery_report_not_found")
report=json.loads(files[-1].read_text())
target="10.10.101.185"
matches=[]
for row in report.get("devices",[]):
    if row.get("discovered_address")!=target or row.get("scanner_returned_id_matches") is not True:
        continue
    entry=local.get(str(row.get("native_id") or "").strip().lower())
    if not entry:continue
    old=entry.get("data",{}).get("host")
    title=str(entry.get("title") or "").strip()
    if "RGBCW" in title.upper():
        label="RGBCW lightbulb"
    elif "RGBW" in title.upper():
        label="RGBW lightbulb"
    else:
        label="different_device"
    matches.append({"ui_entry":label,
                    "config_has_existing_key":bool(entry.get("data",{}).get("local_key")),
                    "new_host_differs_from_configured":old!=target})
reach=False
try:
    with socket.create_connection((target,6668),timeout=1.2) as s:
        reach=True
except OSError:pass
print(json.dumps({"exact_id_matched_entries":len(matches),
                 "matches":matches,"discovered_tuya_port_open":reach,
                 "identity_verified_by_discovery":len(matches)==1,
                 "changes_applied":False}))
'''
def main():
    if "running" not in ssh_host("nodeb",["qm","status","905"]):
        raise RuntimeError("HA-General offline")
    src="exec(__import__('base64').b64decode('"+base64.b64encode(GUEST.encode()).decode()+"'))"
    r=json.loads(ssh_host("nodeb",["qm","guest","exec","905","--","docker","exec","homeassistant","python3","-c",src]))
    pid=r.get("pid");deadline=time.monotonic()+75
    while not r.get("exited"):
        if not isinstance(pid,int) or time.monotonic()>deadline:
            raise RuntimeError("guest agent not responsive")
        time.sleep(2)
        r=json.loads(ssh_host("nodeb",["qm","guest","exec-status","905",str(pid)]))
    if r.get("exitcode")!=0:raise RuntimeError("guest matching failed")
    return json.loads(r.get("out-data",""))
if __name__=="__main__":
    try:print("JNS_TUYA_SCREENSHOT_MATCH",json.dumps(main(),sort_keys=True),flush=True)
    except Exception as e:print("JNS_TUYA_SCREENSHOT_MATCH_BLOCKED",type(e).__name__,flush=True);raise SystemExit(1)
