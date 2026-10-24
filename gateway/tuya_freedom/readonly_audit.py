#!/usr/bin/env python3
"""Read-only Tuya dependency inventory on HA-General VM905.

This workflow emits only aggregate counts. It never prints .storage contents,
entity/device identifiers, hosts, device keys, cloud credentials or user data.
"""
import base64
import json
import sys
import time

sys.path.insert(0, "gateway/arrival_lighting")
from readiness_probe import ssh_host

GUEST = r'''
import collections
import json
import pathlib
import re

root = pathlib.Path("/config/.storage")
result = {"schema": 1, "target": "ha-general", "mode": "read_only"}
def load(filename):
    try:
        payload = json.loads((root / filename).read_text())
        return payload.get("data", {})
    except (OSError, ValueError, TypeError):
        result["missing_or_invalid_" + filename.replace(".", "_")] = True
        return {}

entries = load("core.config_entries").get("entries", [])
entities = load("core.entity_registry").get("entities", [])
devices = load("core.device_registry").get("devices", [])
by_entry = {str(e.get("entry_id")): e.get("domain", "") for e in entries}
tuya_domains = ("tuya", "tuya_local", "localtuya")
entry_counts = collections.Counter(e.get("domain", "unknown") for e in entries)
entity_counts = collections.Counter()
entity_ids_by_domain = collections.defaultdict(set)
for e in entities:
    platform = str(e.get("platform") or "")
    if platform in tuya_domains:
        entity_counts[platform] += 1
        entity_ids_by_domain[platform].add(e.get("entity_id", ""))
dev_counts = collections.Counter()
for d in devices:
    parent = {by_entry.get(str(c), "") for c in d.get("config_entries", [])}
    if "tuya" in parent:
        dev_counts["cloud_tuya"] += 1
    if "tuya_local" in parent:
        dev_counts["tuya_local"] += 1
    if "localtuya" in parent:
        dev_counts["localtuya"] += 1
    manufacturer = str(d.get("manufacturer") or "").lower()
    if "tuya" in manufacturer and "tuya" not in parent:
        dev_counts["tuya_manufacturer_without_cloud_entry"] += 1
        if "mqtt" in parent:
            dev_counts["already_mqtt"] += 1
        if "zha" in parent:
            dev_counts["already_zha"] += 1

def has_field(v, key):
    if isinstance(v, dict):
        return key in v or any(has_field(x, key) for x in v.values())
    if isinstance(v, list):
        return any(has_field(x, key) for x in v)
    return False
result["config_entries"] = {d: entry_counts[d] for d in tuya_domains}
result["devices"] = dict(dev_counts)
result["entities"] = dict(entity_counts)
result["tuya_local_key_entry_count"] = sum(
    bool(has_field(e.get("data", {}), "local_key") or has_field(e.get("options", {}), "local_key"))
    for e in entries if e.get("domain") in tuya_domains
)
result["tuya_cloud_automations_referencing_entity_count"] = 0
result["automations_checked"] = False
f = pathlib.Path("/config/automations.yaml")
if f.is_file():
    raw = f.read_text(errors="replace")
    result["automations_checked"] = True
    result["tuya_cloud_automations_referencing_entity_count"] = sum(
        len(re.findall(r"(?<![\w.])" + re.escape(eid) + r"(?![\w.])", raw))
        for eid in entity_ids_by_domain["tuya"] if eid
    )
result["local_component_dirs"] = {
    d: (pathlib.Path("/config/custom_components") / d).is_dir()
    for d in ("tuya_local", "localtuya")
}

# Registry-based dependency analysis. IDs stay inside the guest.
entry_by_id = {e.get("entry_id"):e for e in entries}
entity_by_platform = collections.defaultdict(list)
for ent in entities:
    entity_by_platform[ent.get("platform") or ""].append(ent)
result["cloud_entity_domains"] = dict(collections.Counter(
    (e.get("entity_id") or "").split(".")[0] for e in entity_by_platform["tuya"]))
result["local_entity_domains"] = dict(collections.Counter(
    (e.get("entity_id") or "").split(".")[0] for e in entity_by_platform["tuya_local"]))
result["cloud_registry_health"] = {
    "entities_with_device_link":sum(bool(e.get("device_id")) for e in entity_by_platform["tuya"]),
    "entities_with_config_entry_link":sum(bool(e.get("config_entry_id")) for e in entity_by_platform["tuya"]),
    "entities_with_existing_config_entry":sum(
        e.get("config_entry_id") in entry_by_id for e in entity_by_platform["tuya"]),
    "devices_with_primary_cloud_entry":sum(
        by_entry.get(str(d.get("config_entry_id")),"")=="tuya" for d in devices)
}
result["local_registry_health"] = {
    "entities_with_device_link":sum(bool(e.get("device_id")) for e in entity_by_platform["tuya_local"]),
    "entities_with_config_entry_link":sum(bool(e.get("config_entry_id")) for e in entity_by_platform["tuya_local"])
}

print(json.dumps(result, sort_keys=True))
'''

def run():
    if "running" not in ssh_host("nodeb", ["qm", "status", "905"]):
        raise RuntimeError("VM905 not running")
    script = "exec(__import__('base64').b64decode('" + base64.b64encode(GUEST.encode()).decode() + "'))"
    command = ["qm", "guest", "exec", "905", "--", "docker", "exec",
               "homeassistant", "python3", "-c", script]
    result = json.loads(ssh_host("nodeb", command))
    end = time.monotonic() + 80
    while not result.get("exited"):
        pid = result.get("pid")
        if not isinstance(pid, int) or time.monotonic() >= end:
            raise RuntimeError("HA guest-agent inspection unavailable")
        time.sleep(1)
        result = json.loads(ssh_host("nodeb", [
            "qm", "guest", "exec-status", "905", str(pid)]))
    if result.get("exitcode") != 0:
        raise RuntimeError("HA read-only inspection failed; no changes attempted")
    return json.loads(result.get("out-data", ""))

if __name__ == "__main__":
    try:
        print("JNS_TUYA_FREEDOM_AUDIT", json.dumps(run(), sort_keys=True), flush=True)
    except Exception as exc:
        print("JNS_TUYA_FREEDOM_AUDIT_BLOCKED", type(exc).__name__, str(exc)[:100],
              flush=True)
        raise SystemExit(1)
