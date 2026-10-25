#!/usr/bin/env python3
"""Cross-check prior exact-ID LAN discovery with current Tuya Local UI card titles.

No private IDs, local addresses, or keys sent to GitHub Actions logs.
The only disclosed labels are those already visible in supplied screenshot.
"""
import base64,json,sys,time
sys.path.insert(0,"gateway/arrival_lighting")
from readiness_probe import ssh_host
GUEST=r'''
import json,pathlib,socket
home=pathlib.Path("/config")
files=sorted((home/".jns_tuya_freedom").glob("udp-discovery-*.json"))
if not files:raise RuntimeError("no_saved_discovery")
doc=json.loads(files[-1].read_text())
data=json.loads((home/".storage/core.config_entries").read_text())["data"]["entries"]
ids={str(c.get("data",{}).get("device_id") or "").lower():c for c in data if c.get("domain")=="tuya_local"}
rows=[]
for match in doc.get("devices",[]):
    native=str(match.get("native_id") or "").lower()
    entry=ids.get(native)
    title=str((entry or {}).get("title") or "")
    label=("RGBCW lightbulb" if "rgbcw" in title.lower() else
          "RGBW lightbulb" if "rgbw" in title.lower() else
          "other_existing_entry" if entry else "no_matching_entry")
    discovered=match.get("discovered_address")
    old=(entry or {}).get("data",{}).get("host")
    reach=False
    if isinstance(discovered,str) and discovered:
        try:
            with socket.create_connection((discovered,6668),timeout=1.2):
                reach=True
        except OSError:pass
    rows.append({
      "ui_label":label,
      "has_matching_existing_entry":bool(entry),
      "exact_id_verified":match.get("scanner_returned_id_matches") is True,
      "discovery_at_different_address":bool(discovered and old!=discovered),
      "new_address_tuya_tcp_open":reach,
      "matches_green_discovery_10_10_101_185":discovered=="10.10.101.185",
      "host_options_changed":False
    })
print(json.dumps({"private_historical_report_count":len(files),
                 "rows":rows,
                 "no_settings_changed":True},sort_keys=True))
'''
def main():
    if "running" not in ssh_host("nodeb",["qm","status","905"]):raise RuntimeError("offline")
    src="exec(__import__('base64').b64decode('"+base64.b64encode(GUEST.encode()).decode()+"'))"
    r=json.loads(ssh_host("nodeb",["qm","guest","exec","905","--","docker","exec","homeassistant","python3","-c",src]))
    pid=r.get("pid");end=time.monotonic()+90
    while not r.get("exited"):
        if not isinstance(pid,int) or time.monotonic()>end:raise RuntimeError("guest_busy")
        time.sleep(2)
        r=json.loads(ssh_host("nodeb",["qm","guest","exec-status","905",str(pid)]))
    if r.get("exitcode")!=0:raise RuntimeError("guest_failed")
    return json.loads(r.get("out-data",""))
if __name__=="__main__":
    try:print("JNS_TUYA_CARD_DISCOVERY_MATCH",json.dumps(main(),sort_keys=True),flush=True)
    except Exception as e:print("JNS_TUYA_CARD_DISCOVERY_MATCH_BLOCKED",type(e).__name__,flush=True);raise SystemExit(1)
