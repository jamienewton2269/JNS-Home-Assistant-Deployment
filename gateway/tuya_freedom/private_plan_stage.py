#!/usr/bin/env python3
"""Generate a JNS VM905 private Tuya cloud/local comparison file.

Saves only to VM905 /config/.jns_tuya_freedom, mode 0600.
Never sends the file or any of its identifiers, names or keys to Actions.
No HA settings, entity IDs, cloud entries or automations are changed.
"""
import base64
import json
import sys
import time

sys.path.insert(0, "gateway/arrival_lighting")
from readiness_probe import ssh_host

GUEST = r'''
import collections
import datetime
import json
import os
from pathlib import Path
import re
root = Path("/config")
stor = root / ".storage"
def load(n, k):
    return json.loads((stor / n).read_text())["data"][k]
cfg = load("core.config_entries", "entries")
entities = load("core.entity_registry", "entities")
devices = load("core.device_registry", "devices")
entries = {e["entry_id"]:e for e in cfg}
ents_by_dev = collections.defaultdict(list)
for e in entities:
    if e.get("device_id"):
        ents_by_dev[e["device_id"]].append(e)
def normalized_ids(d):
    ids = set()
    for item in d.get("identifiers", []):
        if isinstance(item, (list, tuple)) and len(item) == 2:
            v = str(item[1]).strip().lower()
            if len(v) >= 12:
                ids.add(v)
    ce = entries.get(d.get("config_entry_id"), {})
    for f in ("device_id", "id"):
        v = ce.get("data", {}).get(f)
        if isinstance(v, str) and len(v) >= 12:
            ids.add(v.strip().lower())
    return ids
def name(e):
    return e.get("name") or e.get("original_name") or e.get("entity_id", "").split(".")[-1]
def norm(s):
    return re.sub("[^a-z0-9]+", "", str(s or "").lower())
def sample(d):
    es = ents_by_dev.get(d["id"], [])
    return {
        "device_id": d["id"],
        "name": d.get("name_by_user") or d.get("name") or "",
        "model": d.get("model") or "",
        "manufacturer": d.get("manufacturer") or "",
        "config_entry_id": d.get("config_entry_id"),
        "entities": [
            {"entity_id":e.get("entity_id"), "unique_id":e.get("unique_id"),
             "platform":e.get("platform"), "original_name":e.get("original_name"),
             "custom_name":e.get("name"), "disabled_by":e.get("disabled_by")}
            for e in es],
    }
clouds = [d for d in devices if entries.get(d.get("config_entry_id"), {}).get("domain") == "tuya"]
locals_ = [d for d in devices if entries.get(d.get("config_entry_id"), {}).get("domain") == "tuya_local"]
loc_ids = {d["id"]:normalized_ids(d) for d in locals_}
source = []
coverage = collections.Counter()
for d in clouds:
    matches = [l for l in locals_ if normalized_ids(d) & loc_ids[l["id"]]]
    choices = []
    for loc in matches:
        suggestions = []
        for old in ents_by_dev.get(d["id"], []):
            if old.get("platform") != "tuya": continue
            choices_here = [
                e for e in ents_by_dev.get(loc["id"], [])
                if e.get("platform") == "tuya_local"
                and (e.get("entity_id") or "").split(".")[0] ==
                    (old.get("entity_id") or "").split(".")[0]
                and norm(name(e)) == norm(name(old))
            ]
            if len(choices_here) == 1:
                suggestions.append({
                    "old_entity_id":old.get("entity_id"),
                    "local_entity_id":choices_here[0].get("entity_id"),
                    "approved":False,
                    "reason":"name_and_domain_hint_not_confirmed"
                })
        choices.append({"local":sample(loc), "suggestions":suggestions})
    coverage["cloud_with_identifier_candidate" if matches else "no_identifier_candidate"] += 1
    if len(matches) > 1:
        coverage["ambiguous_multiple_local_devices"] += 1
    source.append({"cloud":sample(d), "local_candidates":choices,
                   "local_key_present_in_matched_entry":any(
                       "local_key" in (entries.get(x.get("config_entry_id"),{}).get("data",{}))
                       for x in matches)})
report = {
    "schema":1,
    "generated_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "notice":"PRIVATE FILE; names and IDs must never be committed. No pair approved.",
    "devices":source,
    "counts":dict(coverage),
}
dest = root / ".jns_tuya_freedom"
if dest.is_symlink():
    raise RuntimeError("Unsafe output symlink")
dest.mkdir(mode=0o700, exist_ok=True)
os.chmod(dest, 0o700)
filename = "plan-" + datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".json"
p = dest / filename
fd = os.open(str(p), os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600)
with os.fdopen(fd, "w", encoding="utf-8") as handle:
    json.dump(report, handle, indent=2, sort_keys=True)
    handle.write("\n")
    handle.flush()
    os.fsync(handle.fileno())
print(json.dumps({"staged":True, "device_count":len(clouds),
                  "local_device_count":len(locals_), "summary":dict(coverage),
                  "private_directory":"/config/.jns_tuya_freedom"}))
'''

def main():
    status = ssh_host("nodeb", ["qm", "status", "905"])
    if "running" not in status:
        raise RuntimeError("VM905 not running")
    command = "exec(__import__('base64').b64decode('" + base64.b64encode(GUEST.encode()).decode() + "'))"
    r = json.loads(ssh_host("nodeb", ["qm", "guest", "exec", "905", "--",
        "docker", "exec", "homeassistant", "python3", "-c", command]))
    end = time.monotonic() + 85
    while not r.get("exited"):
        if not isinstance(r.get("pid"), int) or time.monotonic() > end:
            raise RuntimeError("HA QGA operation unavailable")
        time.sleep(1)
        r = json.loads(ssh_host("nodeb", ["qm", "guest", "exec-status",
                                         "905", str(r["pid"])]))
    if r.get("exitcode") != 0:
        raise RuntimeError("private planning failed; no HA configuration touched")
    return json.loads(r.get("out-data", ""))

if __name__ == "__main__":
    try:
        print("JNS_TUYA_PRIVATE_PLAN", json.dumps(main(), sort_keys=True), flush=True)
    except Exception as exc:
        print("JNS_TUYA_PRIVATE_PLAN_BLOCKED", type(exc).__name__,
              str(exc)[:100], flush=True)
        raise SystemExit(1)
