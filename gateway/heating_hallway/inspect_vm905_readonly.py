#!/usr/bin/env python3
"""Source identity and deployment compatibility preflight, read-only on VM905.

Public GitHub logs contain only booleans/counts and source fingerprints.
No auth tokens, device names, raw entity IDs, temperatures, samples or
configuration text are printed. No writes, HA commands, or restarts.
"""
import base64
import json
import sys
import time
sys.path.insert(0, "gateway/arrival_lighting")
from readiness_probe import ssh_host

AUDIT = r'''
import hashlib, json, pathlib, re, sys, yaml
ROOT=pathlib.Path("/config")
HALLWAY_DEVICE_ID="3fc0d19af1ae3fad19d67ae05b4ccb0f"
FIREPLACE_IEEE="0xa4c138818d33ffff"
BATHROOM="sensor.0xa4c1382471d2ed23_temperature"
def records(name,key):
    return json.loads((ROOT/".storage"/name).read_text())["data"][key]
devices=records("core.device_registry","devices")
entities=records("core.entity_registry","entities")
config=records("core.config_entries","entries")
def temps(did):
    return sorted(set(e.get("entity_id","") for e in entities
        if e.get("device_id")==did and not e.get("disabled_by")
        and e.get("entity_id","").startswith("sensor.")
        and ((e.get("device_class") or e.get("original_device_class"))=="temperature"
             or (not e.get("device_class") and not e.get("original_device_class")
                 and e.get("entity_id","").endswith("_temperature")))))
hall=[d for d in devices if d.get("id")==HALLWAY_DEVICE_ID]
hall_ids=temps(HALLWAY_DEVICE_ID)
fire_devices=set()
for d in devices:
    pairs=d.get("identifiers") or []
    if any(FIREPLACE_IEEE in str(z).lower() for pair in pairs for z in pair):
        fire_devices.add(d.get("id"))
for e in entities:
    if FIREPLACE_IEEE in str(e.get("unique_id","")).lower() and e.get("device_id"):
        fire_devices.add(e["device_id"])
fire_ids=sorted(set(eid for did in fire_devices for eid in temps(did)))
def signature(ids):
    return [hashlib.sha256(x.encode()).hexdigest()[:12] for x in ids]
components=ROOT/"custom_components"/"jns_heating_zones"
version="missing"
try: version=json.loads((components/"manifest.json").read_text()).get("version","unknown")
except (OSError,ValueError): pass
heat=[e for e in config if e.get("domain")=="jns_heating_zones"]
refs=ROOT/"packages"/"jns_house_temperature.yaml"
schedule=ROOT/"packages"/"jns_heating_predictive_schedule.yaml"
dashboard=ROOT/"dashboards"/"testing.yaml"
heat_source=[e.get("options",{}).get("temperature_entity",e.get("data",{}).get("temperature_entity","")) for e in heat]
yaml_refs={}
for p in (refs,schedule):
    if p.exists():
        s=p.read_text(errors="replace")
        yaml_refs[p.name]={
            "sha256":hashlib.sha256(p.read_bytes()).hexdigest(),
            "hallway_alias_used": "sensor.jns_hallway_house_temperature" in s,
            "old_house_alias_used": "sensor.jns_house_temperature" in s,
            "bathroom_used": BATHROOM in s,
            "honeywell_indoor_used": "sensor.thermostat_thermostat_indoor_temperature" in s,
            "has_fireplace_guard": "jns_fireplace_override_safe" in s,
        }
dash_views=[]
if dashboard.exists():
    raw=yaml.safe_load(dashboard.read_text())
    dash_views=[v.get("path") for v in raw.get("views",[])]
plant=[e for e in entities if e.get("entity_id","").startswith("sensor.") and
    "temperature" in e.get("entity_id","") and re.search(
        "plant|plot|grow|soil|moisture",e.get("entity_id",""),re.I)]
out={
 "vm":"905","mode":"readonly","heating_component_version":version,
 "heat_config_entry_count":len(heat),
 "heat_source_is_honeywell":len(heat_source)==1 and heat_source[0]=="sensor.thermostat_thermostat_indoor_temperature",
 "heat_source_is_hallway":len(heat_source)==1 and heat_source[0] in hall_ids,
 "hallway_device_id_exactly_one":len(hall)==1,
 "hallway_enabled_temperature_count":len(hall_ids),
 "hallway_temperature_fingerprints":signature(hall_ids),
 "fireplace_device_count":len(fire_devices),
 "fireplace_enabled_temperature_count":len(fire_ids),
 "fireplace_temperature_fingerprints":signature(fire_ids),
 "bathroom_entity_registered":any(e.get("entity_id")==BATHROOM and not e.get("disabled_by") for e in entities),
 "plant_temperature_candidate_count":len(plant),
 "testing_dashboard_exists":dashboard.exists(),
 "testing_temperature_trends_exists":"temperature-trends" in dash_views,
 "testing_view_count":len(dash_views),
 "source_packages":yaml_refs,
 "staged_v036_dirs_count":len(list((ROOT/".jns_heating_backups").glob("v036-*"))) if (ROOT/".jns_heating_backups").is_dir() else 0,
 "hallway_runtime_installed":(components/"hallway_runtime.py").exists(),
 "bathroom_runtime_installed":(components/"bathroom_runtime.py").exists(),
}
print("JNS_HALLWAY_SOURCE_READONLY "+json.dumps(out,sort_keys=True))
'''
def audit():
    status=ssh_host("nodeb",["qm","status","905"]).strip()
    if "running" not in status: raise RuntimeError("VM905 not running")
    py="exec(__import__('base64').b64decode('"+base64.b64encode(AUDIT.encode()).decode()+"'))"
    r=json.loads(ssh_host("nodeb",["qm","guest","exec","905","--","docker","exec","homeassistant","python3","-c",py]))
    deadline=time.monotonic()+75
    while not r.get("exited"):
        if time.monotonic()>deadline or not isinstance(r.get("pid"),int):
            raise RuntimeError("VM905 audit completion unverified")
        time.sleep(2)
        r=json.loads(ssh_host("nodeb",["qm","guest","exec-status","905",str(r["pid"])]))
    if r.get("exitcode")!=0: raise RuntimeError("VM905 source inspection failed")
    output=r.get("out-data") or ""
    if not output.startswith("JNS_HALLWAY_SOURCE_READONLY "):
        raise RuntimeError("Unexpected audit response")
    print(output,flush=True)
if __name__=="__main__":
    audit()
