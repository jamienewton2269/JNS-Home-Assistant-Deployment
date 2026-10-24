#!/usr/bin/env python3
"""Discover Tuya WiFi broadcasts on HA-General and privately match the seven missing IDs.

Read-only UDP discovery (no cloud login, no keys, no device commands).
Non-discovery does not prove Zigbee or unsupported hardware.
"""
import base64,json,sys,time
sys.path.insert(0,"gateway/arrival_lighting")
from readiness_probe import ssh_host
GUEST=r'''
import collections,datetime,json,os,pathlib
import tinytuya
root=pathlib.Path("/config/.jns_tuya_freedom")
live=json.loads((root/"latest-live.json").read_text())
now=datetime.datetime.now(datetime.timezone.utc)
if not 0<=(now-datetime.datetime.fromisoformat(live["generated_utc"])).total_seconds()<=900:
    raise RuntimeError("observer_stale")
pending={str(x.get("native_device_id","")).strip().lower():x
 for x in live.get("physical_devices",[]) if not x.get("local_configured")}
if len(pending)!=7:raise RuntimeError("expected_seven_pending_devices")
# The public API listens for Tuya UDP discovery once, without connecting to
# any device's control port. Do not output results to GitHub runner logs.
found=tinytuya.deviceScan(False,10)
if not isinstance(found,dict):raise RuntimeError("unexpected_discovery_format")
visible={}
for info in found.values():
    if not isinstance(info,dict):continue
    device_id=str(info.get("gwId") or info.get("id") or "").strip().lower()
    if device_id:
        visible[device_id]={
            "ip":info.get("ip"),"version":info.get("version"),
            "product_id":info.get("productKey") or info.get("product_id")}
rows=[]
counts=collections.Counter()
lines=["# Tuya Freedom — seven-device LAN discovery","",
       "Generated from local UDP discovery only, not cloud authentication.",
       "A device not found could be Zigbee, BLE, asleep, powered off or on another LAN.",
       ""]
for nid,row in sorted(pending.items()):
    info=visible.get(nid)
    name=row.get("name") or "Unnamed Tuya device"
    counts["seven_targets"]+=1
    counts["lan_broadcast_detected" if info else "not_found_in_lan_scan"]+=1
    status="WiFi_LAN_candidate_needs_local_key" if info else "transport_unconfirmed"
    lines.extend(["## "+name,"",
       "- Native Tuya ID: "+nid,
       "- Assessment: "+status,
       "- Discovered address: "+str(info.get("ip") if info else "not available"),
       "- Protocol advertised: "+str(info.get("version") if info else "not available"),
       "- Next: Cloud-assisted Tuya Local setup for direct WiFi candidates; otherwise verify hub Zigbee/BLE, and use Zigbee2MQTT when supported.",
       ""])
    rows.append({"native_id":nid,"name":name,"status":status,"lan_details":info,
                 "safe_to_cutover":False,"requires_one_time_cloud_assisted_key":True})
path=root/("pending-seven-lan-"+now.strftime("%Y%m%dT%H%M%SZ")+".json")
fd=os.open(str(path),os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
with os.fdopen(fd,"w") as f:
    json.dump({"utc":now.isoformat(),"counts":dict(counts),"targets":rows},f,indent=2,sort_keys=True)
    f.write("\n")
target=root/"PENDING_SEVEN_LAN.md"
tmp=root/".PENDING_SEVEN_LAN.new"
if target.is_symlink() or tmp.exists():raise RuntimeError("unsafe_output")
fd=os.open(str(tmp),os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
with os.fdopen(fd,"w") as f:
    f.write("\n".join(lines))
    f.flush()
    os.fsync(f.fileno())
os.replace(tmp,target);os.chmod(target,0o600)
print(json.dumps({"status":"SEVEN_DEVICE_DISCOVERY_COMPLETED",
                  "counts":dict(counts),"private_reports_created":True,
                  "config_changes":False,"cloud_accounts_accessed":False},sort_keys=True))
'''
def main():
    if "running" not in ssh_host("nodeb",["qm","status","905"]):
        raise RuntimeError("vm905_offline")
    src="exec(__import__('base64').b64decode('"+base64.b64encode(GUEST.encode()).decode()+"'))"
    r=json.loads(ssh_host("nodeb",["qm","guest","exec","905","--","docker","exec","homeassistant","python3","-c",src]))
    pid=r.get("pid");stop=time.monotonic()+135
    while not r.get("exited"):
        if not isinstance(pid,int) or time.monotonic()>stop:raise RuntimeError("qga_timeout")
        time.sleep(2)
        r=json.loads(ssh_host("nodeb",["qm","guest","exec-status","905",str(pid)]))
    if r.get("exitcode")!=0:raise RuntimeError("guest_scan_failed")
    return json.loads(r.get("out-data",""))
if __name__=="__main__":
    try:print("JNS_TUYA_SEVEN_LAN_SCAN",json.dumps(main(),sort_keys=True),flush=True)
    except Exception as e:
        print("JNS_TUYA_SEVEN_LAN_SCAN_BLOCKED",type(e).__name__,str(e)[:80],flush=True)
        raise SystemExit(1)
