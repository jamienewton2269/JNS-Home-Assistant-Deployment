#!/usr/bin/env python3
"""Produce a 100% cloud-free local Tuya recovery plan privately on HA-General.

No device commands, login, cloud calls, pairing, restarts or config edits.
"""
import base64,json,sys,time
sys.path.insert(0,"gateway/arrival_lighting")
from readiness_probe import ssh_host
GUEST=r'''
import datetime,ipaddress,json,os,pathlib,socket
folder=pathlib.Path("/config/.jns_tuya_freedom")
live=json.loads((folder/"latest-live.json").read_text())
files=sorted(folder.glob("offline-recovery-*.json"))
if not files:raise RuntimeError("cloudless_inventory_missing")
private=json.loads(files[-1].read_text())
byid={str(r.get("tuya_id") or "").lower():r for r in private.get("devices",[])}
today=datetime.datetime.now(datetime.timezone.utc)
age=(today-datetime.datetime.fromisoformat(live["generated_utc"])).total_seconds()
if not 0<=age<=1200:raise RuntimeError("observer_stale")
lines=["# JNS Tuya Freedom — CLOUD-FREE RECOVERY",
       "",
       "Local operation takes priority. **Do not request Tuya or Smart Life login.**",
       "Private physical-device details. Never publish this file or saved keys.",
       "Generated UTC: "+today.isoformat(),"",
       "## Existing Tuya Local devices",""]
stats={"local":0,"missing":0,"identified_moved_address":0}
for r in live.get("physical_devices",[]):
    nid=str(r.get("native_device_id") or "").lower()
    info=byid.get(nid,{})
    name=info.get("name") or r.get("name") or "Unlabelled device"
    available=int(r.get("available_local_entities") or 0)
    total=int(r.get("enabled_local_entities") or 0)
    if not r.get("local_configured"):continue
    stats["local"]+=1
    status="no local entities available" if available==0 else "partially available" if available<total else "all enabled entities available"
    lines.extend(["### "+name+" — "+status,"",
        "- Available local entities: "+str(available)+"/"+str(total),
        "- Configured local host: "+str(info.get("local_host") or "(unknown)"),
        "- Local key saved: "+str(info.get("local_key_present",False)),
        "- No Tuya account or Tuya-cloud API required for this existing configuration."])
    disc=info.get("discovery") or {}
    proposed=disc.get("discovered_address")
    if proposed and proposed!=info.get("local_host") and disc.get("scanner_returned_id_matches") is True:
        stats["identified_moved_address"]+=1
        resolved=None
        try:
            reverse=socket.gethostbyaddr(proposed)[0]
            ips={x[4][0] for x in socket.getaddrinfo(reverse,6668,type=socket.SOCK_STREAM)}
            if proposed in ips and reverse.endswith(".home.arpa"):resolved=reverse
        except OSError:pass
        lines.extend([
          "- **Verified same physical ID found at NEW address:** "+str(proposed),
          "- DNS-name-first option: "+str(resolved or "No verified home.arpa reverse-forward DNS mapping; repair DNS if possible"),
          "- **Repair:** HA-General → Settings → Devices & Services → Tuya Local → existing device → Configure.",
          "- Change Host only to the verified new DNS name/IP. Preserve the existing key, protocol, type, entity IDs, and data points.",
          "- Recheck the observer after the device reconnects; do not remove any local entity."
        ])
    elif available==0:
        lines.extend([
          "- Not discovered at a safe alternative address.",
          "- Check actual device power, network/Wi-Fi, and pairing network before attempting resets.",
          "- Do not overwrite its local key: a re-pair can rotate the key and break recovery."
        ])
    lines.append("")
lines.extend(["## Seven devices without local configuration","",
              "These are not made locally usable simply by deleting the cloud integration.",
              "No supported direct-WiFi local key has been recovered for them yet.",
              "A single Tuya UDP LAN scan did not locate any of these seven; that does not prove they are Zigbee.",
              ""])
for r in live.get("physical_devices",[]):
    if r.get("local_configured"):continue
    stats["missing"]+=1
    info=byid.get(str(r.get("native_device_id") or "").lower(),{})
    name=info.get("name") or r.get("name") or "Unlabelled device"
    models=info.get("models") or []
    domains=info.get("cloud_domains") or []
    zigbee_hint=any(str(m).upper().startswith(("TS0","TY0","ZB","ZIGBEE")) for m in models)
    lines.extend(["### "+name,"",
                  "- Model(s): "+(", ".join(map(str,models)) if models else "not recorded"),
                  "- Previous HA categories: "+(", ".join(map(str,domains)) if domains else "not recorded"),
                  "- Transport: **not verified**"+(" (model suggests possible Zigbee)" if zigbee_hint else ""),
                  "- Step 1 (physical, offline): Check label/manual for Zigbee / Wi-Fi / BLE / Matter.",
                  "- Zigbee: confirm coordinator CT214 is running; use Zigbee2MQTT Permit join for a short, controlled window, reset and join this exact device physically. Preserve existing MQTT and area naming. No Tuya key or account needed.",
                  "- Matter: onboard to your supported local Matter controller if device/hub supports it.",
                  "- Wi-Fi Tuya firmware: without an existing valid local_key, direct Tuya Local control cannot be provisioned purely from device ID/IP. Look for previously saved key in original backups, or evaluate supported replacement firmware/hardware.",
                  "- BLE: investigate supported native Bluetooth support; avoid assuming direct LAN control.",
                  "- Do not factory reset Wi-Fi devices merely to try local pairing; it may change an existing key.",
                  "- Cloud removal and entity-ID cutover: **defer until an independently verified local replacement exists**.",
                  ""])
lines.extend(["## Controls and next verification","",
              "1. Repair the verified moved Tuya Local host first via the supported integration Configure flow, without restarting Home Assistant.",
              "2. Verify live states in /config/.jns_tuya_freedom/latest-live.json (updated every five minutes).",
              "3. Inventory physical radio type for each of the seven. Never bulk-reset; join Zigbee devices individually.",
              "4. After control is proven, conduct one-device-at-a-time WAN-blocked tests and preserve rollback.",
              "5. Disable/delete native Tuya cloud config entries only when no local automations still depend on them.",
              "",
              "Security: any Home Assistant long-lived token previously pasted into a conversation should be revoked.",
              ""])
path=folder/"CLOUDLESS_RECOVERY_STATUS.md"
if path.is_symlink():raise RuntimeError("unsafe_report_symlink")
temp=folder/".CLOUDLESS_RECOVERY_STATUS.new"
fd=os.open(str(temp),os.O_CREAT|os.O_EXCL|os.O_WRONLY|getattr(os,"O_NOFOLLOW",0),0o600)
with os.fdopen(fd,"w") as output:
    output.write("\n".join(lines)+"\n");output.flush();os.fsync(output.fileno())
os.replace(temp,path)
os.chmod(path,0o600)
print(json.dumps({"status":"CLOUD_FREE_PLAN_STAGED","summary":stats,
                  "private_report_path":"/config/.jns_tuya_freedom/CLOUDLESS_RECOVERY_STATUS.md",
                  "tuya_cloud_accessed":False,"devices_changed":0}))
'''
def main():
    if "running" not in ssh_host("nodeb",["qm","status","905"]):raise RuntimeError("vm905_offline")
    cmd="exec(__import__('base64').b64decode('"+base64.b64encode(GUEST.encode()).decode()+"'))"
    r=json.loads(ssh_host("nodeb",["qm","guest","exec","905","--","docker","exec","homeassistant","python3","-c",cmd]))
    pid=r.get("pid");limit=time.monotonic()+100
    while not r.get("exited"):
        if not isinstance(pid,int) or time.monotonic()>limit:raise RuntimeError("qga_timeout")
        time.sleep(2)
        r=json.loads(ssh_host("nodeb",["qm","guest","exec-status","905",str(pid)]))
    if r.get("exitcode")!=0:raise RuntimeError("stage_failed")
    return json.loads(r.get("out-data",""))
if __name__=="__main__":
    try:print("JNS_TUYA_CLOUD_FREE_PLAN",json.dumps(main(),sort_keys=True),flush=True)
    except Exception as e:
        print("JNS_TUYA_CLOUD_FREE_PLAN_BLOCKED",type(e).__name__,flush=True)
        raise SystemExit(1)
