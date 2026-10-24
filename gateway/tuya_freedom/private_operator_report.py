#!/usr/bin/env python3
"""Prepare a private operator-facing report from the tokenfree live observer.

Details stay inside VM905 /config/.jns_tuya_freedom, never in Actions output.
"""
import base64,json,sys,time
sys.path.insert(0,"gateway/arrival_lighting")
from readiness_probe import ssh_host
GUEST=r'''
import collections,datetime,json,os,pathlib
root=pathlib.Path("/config")
private=root/".jns_tuya_freedom"
report=private/"latest-live.json"
if not report.is_file() or report.is_symlink():
    raise RuntimeError("No live observer result")
data=json.loads(report.read_text())
if data.get("mode")!="in_process_read_only":
    raise RuntimeError("Observer report not confirmed")
ts=datetime.datetime.fromisoformat(data["generated_utc"])
age=(datetime.datetime.now(datetime.timezone.utc)-ts).total_seconds()
if not 0<=age<=750:
    raise RuntimeError("Observer data too old")
configs=json.loads((root/".storage/core.config_entries").read_text())["data"]["entries"]
devices=json.loads((root/".storage/core.device_registry").read_text())["data"]["devices"]
entities=json.loads((root/".storage/core.entity_registry").read_text())["data"]["entities"]
entries={e["entry_id"]:e for e in configs}
cloud_reg=collections.defaultdict(list)
for dev in devices:
    if not any(entries.get(eid,{}).get("domain")=="tuya" for eid in dev.get("config_entries",[])):
        continue
    for domain,value in dev.get("identifiers",[]):
        if str(domain).lower()=="tuya" and len(str(value))>=12:
            cloud_reg[str(value).strip().lower()].append(dev)
local=collections.defaultdict(list)
for row in data.get("physical_devices",[]):
    local["configured" if row.get("local_configured") else "missing"].append(row)
lines=[
    "# Tuya Freedom — HA-General private operator report",
    "",
    "Read-only live state inspection (NOT proof of WAN isolation or functional command control).",
    "Generated UTC: "+data["generated_utc"],
    "",
    "## Existing five — local status",
    "",
]
for row in local["configured"]:
    total=int(row.get("enabled_local_entities") or 0)
    ok=int(row.get("available_local_entities") or 0)
    name=row.get("name") or "(unnamed device)"
    status=("NO_AVAILABLE_ENTITIES" if ok==0 else "PARTIAL" if ok<total else "AVAILABLE")
    lines.extend([f"### {name} — {status} ({ok}/{total} available)", ""])
    for entity,state in sorted((row.get("local_entity_states") or {}).items()):
        lines.append("- "+entity+": "+state)
    lines.extend(["", "Keep cloud entities intact; investigate unavailable readings first.",""])
lines.extend(["## Seven devices requiring onboarding","","No local key has been recovered for these devices from native HA cloud configuration.",""])
for row in local["missing"]:
    name=row.get("name") or "(unnamed device)"
    ds=cloud_reg.get(str(row.get("native_device_id") or "").lower(),[])
    models=sorted({str(d.get("model")) for d in ds if d.get("model")})
    manufacturers=sorted({str(d.get("manufacturer")) for d in ds if d.get("manufacturer")})
    linked=set(d.get("id") for d in ds)
    cloud_entities=sorted({
        e.get("entity_id") for e in entities
        if e.get("platform")=="tuya" and e.get("device_id") in linked and e.get("entity_id")
    })
    lines.extend([f"### {name}","",
                  "- Model: "+(", ".join(models) if models else "not recorded"),
                  "- Manufacturer: "+(", ".join(manufacturers) if manufacturers else "not recorded"),
                  "- Tuya physical ID (keep local): "+str(row.get("native_device_id") or "unknown"),
                  "- Transport/protocol: **NOT YET VERIFIED** (Wi-Fi vs hub-mediated Zigbee/BLE)",
                  "- Cloud entities: "+(", ".join(cloud_entities) if cloud_entities else "none"),
                  "- Next step: Determine transport. For supported Wi-Fi devices use Tuya Local's one-time Smart Life/Tuya assisted authorisation in Home Assistant UI. For native Zigbee choose Zigbee2MQTT where feasible rather than inventing a Wi-Fi local key.",
                  "- Do not re-pair a working device, actuate locks/security equipment or remove its existing cloud entry without backup and rollback.",
                  ""])
lines.extend(["## Migration gates","",
              "1. Resolve local 0-available and partially unavailable devices.",
              "2. Determine actual transport and local support for each of seven missing devices.",
              "3. Onboard through supported Home Assistant Tuya Local config flows or Zigbee2MQTT; never put credentials in GitHub.",
              "4. Verify correct same-device DP/entity mapping with physical testing.",
              "5. Prove device works with WAN blocked, then consider transactional entity-ID cutover.",
              "6. Keep original Tuya cloud integrations until all dependent entities are replaced.",
              ""])
payload=("\n".join(lines)+"\n").encode()
if private.is_symlink():
    raise RuntimeError("Unsafe output directory")
output=private/"ONBOARDING_STATUS.md"
if output.is_symlink():
    raise RuntimeError("Unsafe output symlink")
tmp=private/".ONBOARDING_STATUS.tmp"
fd=os.open(str(tmp),os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,"O_NOFOLLOW",0),0o600)
try:
    with os.fdopen(fd,"wb") as f:
        f.write(payload)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp,output)
    os.chmod(output,0o600)
finally:
    if tmp.exists():tmp.unlink()
tot=data.get("aggregate",{})
print(json.dumps({"private_report_created":True,
                  "existing_local_devices":len(local["configured"]),
                  "missing_local_devices":len(local["missing"]),
                  "local_devices_with_some_available":tot.get("local_devices_with_available_entity",0),
                  "report_path":"/config/.jns_tuya_freedom/ONBOARDING_STATUS.md",
                  "contains_secret_keys":False}))
'''
def main():
    if "running" not in ssh_host("nodeb",["qm","status","905"]):
        raise RuntimeError("vm905_offline")
    src="exec(__import__('base64').b64decode('"+base64.b64encode(GUEST.encode()).decode()+"'))"
    res=json.loads(ssh_host("nodeb",["qm","guest","exec","905","--","docker","exec","homeassistant","python3","-c",src]))
    pid=res.get("pid")
    expiry=time.monotonic()+90
    while not res.get("exited"):
        if not isinstance(pid,int) or time.monotonic()>expiry:
            raise RuntimeError("vm905_guest_agent_report_timeout")
        time.sleep(2)
        res=json.loads(ssh_host("nodeb",["qm","guest","exec-status","905",str(pid)]))
    if res.get("exitcode")!=0:
        raise RuntimeError("private_report_generation_failed")
    return json.loads(res.get("out-data",""))
if __name__=="__main__":
    try:print("JNS_TUYA_PRIVATE_OPERATOR_REPORT",json.dumps(main(),sort_keys=True),flush=True)
    except Exception as e:
        print("JNS_TUYA_PRIVATE_OPERATOR_REPORT_BLOCKED",type(e).__name__,str(e)[:95],flush=True)
        raise SystemExit(1)
