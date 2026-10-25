#!/usr/bin/env python3
"""Private, cloud-independent recovery audit for Tuya on JNS HA-General.

Uses HA registries, offline LAN discovery records, HA observer snapshots and
Zigbee2MQTT's existing device records. No cloud access, pairing or device commands.
No private identifiers, keys, hosts or names leave VM905 / Node B.
"""
import base64,json,sys,time
sys.path.insert(0,"gateway/arrival_lighting")
from readiness_probe import ssh_host

HA=r'''
import collections,datetime,ipaddress,json,os,pathlib,re
root=pathlib.Path("/config")
private=root/".jns_tuya_freedom"
configs=json.loads((root/".storage/core.config_entries").read_text())["data"]["entries"]
devices=json.loads((root/".storage/core.device_registry").read_text())["data"]["devices"]
entities=json.loads((root/".storage/core.entity_registry").read_text())["data"]["entities"]
observer=json.loads((private/"latest-live.json").read_text())
latest_discovery=sorted(private.glob("udp-discovery-*.json"))
disc=json.loads(latest_discovery[-1].read_text()) if latest_discovery else {}
cloudids={e["entry_id"] for e in configs if e.get("domain")=="tuya"}
def norm(s):return re.sub(r"[^a-z0-9]","",str(s or "").lower())
def cloud_match(d):return bool(({d.get("config_entry_id")}|set(d.get("config_entries",[])))&cloudids)
byid=collections.defaultdict(list)
for d in devices:
    if cloud_match(d):
        for namespace,value in d.get("identifiers",[]):
            if namespace=="tuya" and len(str(value))>=12:byid[str(value).lower()].append(d)
bydev=collections.defaultdict(list)
for e in entities:bydev[e.get("device_id")].append(e)
dlist=disc.get("devices",[])
knownlocal={str(e.get("data",{}).get("device_id") or "").lower():e
            for e in configs if e.get("domain")=="tuya_local"}
result=[]
agg=collections.Counter()
otherdevices=[]
for d in devices:
    if cloud_match(d):continue
    parents=set(d.get("config_entries",[]))
    platforms={e.get("platform") for e in bydev.get(d.get("id"),[])}
    if "mqtt" in platforms or any(e.get("domain")=="mqtt" and e.get("entry_id") in parents for e in configs):
        otherdevices.append({"name":d.get("name_by_user") or d.get("name") or "",
                             "model":d.get("model") or "",
                             "manufacturer":d.get("manufacturer") or "",
                             "entity_domains":sorted({x.get("entity_id","").split(".")[0] for x in bydev.get(d.get("id"),[])})})
for d in observer.get("physical_devices",[]):
    nid=str(d.get("native_device_id") or "").lower()
    clouds=byid.get(nid,[])
    names=sorted({c.get("name_by_user") or c.get("name") for c in clouds if c.get("name_by_user") or c.get("name")})
    models=sorted({c.get("model") for c in clouds if c.get("model")})
    manufacturers=sorted({c.get("manufacturer") for c in clouds if c.get("manufacturer")})
    cloudentities=[x for c in clouds for x in bydev.get(c.get("id"),[]) if x.get("platform")=="tuya"]
    local=d.get("local_configured")
    match=[x for x in dlist if str(x.get("native_id") or "").lower()==nid]
    stored=knownlocal.get(nid)
    other=[x for x in otherdevices if any(
         norm(x["name"])==norm(name) and len(norm(name))>=6 for name in names)]
    agg["physical_devices"]+=1
    agg["local_five" if local else "not_local_seven"]+=1
    agg["other_mqtt_same_name_candidates"]+=int(bool(other))
    if not local:
        domains={x.get("entity_id","").split(".")[0] for x in cloudentities}
        agg["nonlocal_with_binary_sensor"]+=int("binary_sensor" in domains)
        agg["nonlocal_with_light"]+=int("light" in domains)
        agg["nonlocal_with_sensor"]+=int("sensor" in domains)
    else:
        good=int(d.get("available_local_entities") or 0)
        agg["existing_local_zero_available"]+=int(good==0)
        agg["existing_local_some_available"]+=int(good>0)
        if match and match[0].get("discovered_address"):
            agg["zero_local_discovered_new_ip"]+=int(
                match[0]["discovered_address"]!=(stored or {}).get("data",{}).get("host"))
            agg["discovery_identity_explicitly_matched"]+=int(match[0].get("scanner_returned_id_matches") is True)
            agg["discovery_identity_missing"]+=int(match[0].get("scanner_returned_id_matches") is None)
    entry={"tuya_id":nid,"name":names[0] if names else "(unnamed)","models":models,
            "manufacturers":manufacturers,
            "cloud_domains":sorted({e.get("entity_id","").split(".")[0] for e in cloudentities}),
            "existing_local":bool(local),
            "existing_local_available":d.get("available_local_entities") if local else None,
            "local_host":(stored or {}).get("data",{}).get("host") if local else None,
            "discovery":match[0] if match else None,
            "mqtt_same_name_candidates":other,"cloud_category_known":bool(cloudentities),
            "local_key_present":bool((stored or {}).get("data",{}).get("local_key")),
            "local_method":"existing_tuya_local" if local else "requires_key_or_non_tuya_local_transport",
            "action_permitted":False}
    result.append(entry)
now=datetime.datetime.now(datetime.timezone.utc)
path=private/("offline-recovery-"+now.strftime("%Y%m%dT%H%M%SZ")+".json")
fd=os.open(str(path),os.O_CREAT|os.O_EXCL|os.O_WRONLY|getattr(os,"O_NOFOLLOW",0),0o600)
with os.fdopen(fd,"w") as f:json.dump({"utc":now.isoformat(),"summary":dict(agg),"devices":result,
    "note":"Cloud-free matching only; do not publish names IDs or hosts. No configuration changes."},f,indent=2)
print(json.dumps({"status":"PRIVATE_CLOUD_FREE_AUDIT","aggregate":dict(agg),
                  "report_private":True,"cloud_accessed":False,"devices_changed":0}))
'''
def run_guest(args,limit=90):
    r=json.loads(ssh_host("nodeb",["qm","guest","exec","905","--",*args]))
    pid=r.get("pid");end=time.monotonic()+limit
    while not r.get("exited"):
        if not isinstance(pid,int) or time.monotonic()>end:raise RuntimeError("guest_response_timeout")
        time.sleep(2)
        r=json.loads(ssh_host("nodeb",["qm","guest","exec-status","905",str(pid)]))
    if r.get("exitcode")!=0:raise RuntimeError("ha_guest_audit_failed")
    return json.loads(r.get("out-data",""))
def main():
    if "running" not in ssh_host("nodeb",["qm","status","905"]):raise RuntimeError("vm905_offline")
    if "running" not in ssh_host("nodeb",["pct","status","214"]):
        zigbee={"status":"zigbee2mqtt_container_not_running"}
    else:
        # Read-only container visibility check, no device/secret data to runner.
        cmd="for p in /opt/zigbee2mqtt/data/database.db /var/lib/zigbee2mqtt/data/database.db /app/data/database.db /data/database.db; do if test -f \"$p\"; then echo 'database_present'; exit 0; fi; done; echo 'database_location_unknown'"
        try:
            status=ssh_host("nodeb",["pct","exec","214","--","sh","-c",cmd]).strip()
            zigbee={"status":status if status in ("database_present","database_location_unknown") else "unknown"}
        except Exception:zigbee={"status":"container_inspection_unavailable"}
    encoded=base64.b64encode(HA.encode()).decode()
    result=run_guest(["docker","exec","homeassistant","python3","-c",
                      "exec(__import__('base64').b64decode('"+encoded+"'))"])
    result["ct214"]=zigbee
    return result
if __name__=="__main__":
    try:print("JNS_TUYA_OFFLINE_RECOVERY",json.dumps(main(),sort_keys=True),flush=True)
    except Exception as exc:
        print("JNS_TUYA_OFFLINE_RECOVERY_BLOCKED",type(exc).__name__,flush=True)
        raise SystemExit(1)
