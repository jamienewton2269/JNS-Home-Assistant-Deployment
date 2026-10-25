#!/usr/bin/env python3
"""JNS Tuya Freedom: portable, conservative Home Assistant cloud -> local migration.

Requires: python3 -m pip install websocket-client
Uses HA's authenticated WebSocket API. Default operations are read-only.
No cloud keys, private Tuya identifiers or HA tokens are printed or uploaded.
"""
import argparse
import json
import os
from pathlib import Path
import re
import sys
import time
from urllib.parse import urlsplit

CLOUD = "tuya"
LOCAL = {"tuya_local", "localtuya"}
BAD_STATES = {"unknown", "unavailable"}
SCHEMA = 1


class MigrationError(RuntimeError):
    pass


def secure_write(file, obj):
    """Atomically write private migration information with mode 0600."""
    path = Path(file).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp-" + str(os.getpid()))
    fd = os.open(str(temp), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=2, sort_keys=True)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
        os.chmod(path, 0o600)
    finally:
        if temp.exists():
            temp.unlink()


def load_json(file):
    with open(file, encoding="utf-8") as f:
        return json.load(f)


def norm(value):
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def entity_name(e):
    return e.get("name") or e.get("original_name") or e.get("entity_id", "").split(".", 1)[-1]


class HA:
    def __init__(self, url, token):
        from websocket import create_connection
        u = urlsplit(url.rstrip("/"))
        if u.scheme not in {"http", "https"} or not u.hostname:
            raise MigrationError("HA URL must start http:// or https://")
        ws = ("wss" if u.scheme == "https" else "ws") + "://" + u.netloc + u.path.rstrip("/") + "/api/websocket"
        self.socket = create_connection(ws, timeout=25, enable_multithread=True)
        if json.loads(self.socket.recv()).get("type") != "auth_required":
            raise MigrationError("HA WebSocket authentication handshake failed")
        self.socket.send(json.dumps({"type": "auth", "access_token": token}))
        if json.loads(self.socket.recv()).get("type") != "auth_ok":
            raise MigrationError("HA authentication failed")
        self.next_id = 0

    def call(self, kind, **kw):
        self.next_id += 1
        num = self.next_id
        self.socket.send(json.dumps({"id": num, "type": kind, **kw}))
        while True:
            data = json.loads(self.socket.recv())
            if data.get("id") != num or data.get("type") != "result":
                continue
            if not data.get("success"):
                err = data.get("error") or {}
                raise MigrationError(kind + ": " + str(err.get("code", "error")))
            return data.get("result")

    def inventory(self):
        entities = self.call("config/entity_registry/list")
        devices = self.call("config/device_registry/list")
        states = self.call("get_states")
        if not isinstance(entities, list) or not isinstance(devices, list):
            raise MigrationError("HA registry schema unexpected")
        return entities, devices, {s["entity_id"]: s.get("state") for s in states}

    def close(self):
        self.socket.close()


def snapshot(ha):
    es, ds, states = ha.inventory()
    by_dev = {d["id"]: d for d in ds}
    data = {"schema": SCHEMA, "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "cloud": [], "local": [], "preexisting_local": [], "scope": "Home Assistant Tuya migration"}
    for e in es:
        p = e.get("platform", "")
        dev = by_dev.get(e.get("device_id"), {})
        item = {
            "entity_id": e.get("entity_id"),
            "platform": p,
            "friendly_name": entity_name(e),
            "device_name": dev.get("name_by_user") or dev.get("name"),
            "device_id": e.get("device_id"),
            "config_entry_id": e.get("config_entry_id"),
            "domain": (e.get("entity_id") or "").split(".")[0],
            "state": states.get(e.get("entity_id"), "not_loaded"),
            "disabled_by": e.get("disabled_by"),
            "area_id": e.get("area_id") or dev.get("area_id"),
            "labels": e.get("labels") or [],
        }
        if p == CLOUD:
            data["cloud"].append(item)
        elif p in LOCAL:
            data["local"].append(item)
        elif p in ("mqtt", "zha", "matter"):
            if "tuya" in str(dev.get("manufacturer") or "").lower():
                data["preexisting_local"].append(item)
    return data


def propose(data):
    """Name-based hints only. Never autoapprove a physical-device pairing."""
    pairs = []
    for old in data["cloud"]:
        if old["disabled_by"]:
            continue
        possible = [
            new for new in data["local"]
            if new["domain"] == old["domain"]
            and not new["disabled_by"]
            and (norm(new["friendly_name"]) == norm(old["friendly_name"])
                 or (old.get("device_name") and norm(old["device_name"]) == norm(new.get("device_name"))))
        ]
        if len(possible) == 1:
            pairs.append({
                "cloud": old["entity_id"], "local": possible[0]["entity_id"],
                "confidence": "name_hint_not_verified", "approved": False
            })
    return {
        "schema": SCHEMA,
        "explanation": "Set approved=true only after confirming the SAME physical device and datapoint.",
        "mappings": pairs,
    }


def validate_mappings(proposal, es, states, require_ready=True):
    if proposal.get("schema") != SCHEMA:
        raise MigrationError("Unexpected mapping schema")
    by_id = {e["entity_id"]: e for e in es}
    used = set()
    mappings = proposal.get("mappings")
    if not isinstance(mappings, list) or not mappings:
        raise MigrationError("No mappings supplied")
    for pair in mappings:
        old, new = pair.get("cloud"), pair.get("local")
        if not pair.get("approved") or not old or not new or old == new:
            raise MigrationError("Every mapping must be explicitly approved and distinct")
        if old in used or new in used:
            raise MigrationError("Duplicate entity in mappings")
        used.update([old, new])
        if old not in by_id or new not in by_id:
            raise MigrationError("An entity is not in the current registry")
        a, b = by_id[old], by_id[new]
        if a.get("platform") != CLOUD or b.get("platform") not in LOCAL:
            raise MigrationError("Expected Tuya-cloud source and local target platforms")
        if old.split(".")[0] != new.split(".")[0]:
            raise MigrationError("Cannot replace different entity domains")
        if require_ready and (states.get(new) in BAD_STATES or new not in states):
            raise MigrationError("Local entity not available for a mapping")
    return mappings


def unique_backup(entity_id, existing):
    base = entity_id + "_tuya_cloud_backup"
    candidate = base
    i = 2
    while candidate in existing:
        candidate = base + "_" + str(i)
        i += 1
    existing.add(candidate)
    return candidate


def metadata_snapshot(entity):
    """Capture editable entity metadata for reversible presentation preservation."""
    return {k: entity[k] for k in ("name", "area_id", "icon", "labels")
            if k in entity and entity[k] is not None}


def apply_metadata(ha, entity_id, data):
    if data:
        ha.call("config/entity_registry/update", entity_id=entity_id, **data)


def rollback_operations(ha, journal):
    """Best-effort reverse rename, handling interruptions during each operation."""
    for pair in reversed(journal["mappings"]):
        old, local, backup = pair["cloud"], pair["local"], pair["backup"]
        ents, _, _ = ha.inventory()
        by_id = {e["entity_id"]: e for e in ents}
        # The local entity currently owns the former cloud ID.
        if old in by_id and by_id[old].get("platform") in LOCAL:
            if local not in by_id:
                ha.call("config/entity_registry/update", entity_id=old, new_entity_id=local)
                apply_metadata(ha, local, pair.get("local_metadata", {}))
        ents, _, _ = ha.inventory()
        by_id = {e["entity_id"]: e for e in ents}
        if backup in by_id and by_id[backup].get("platform") == CLOUD and old not in by_id:
            ha.call("config/entity_registry/update", entity_id=backup, new_entity_id=old)


def cutover(ha, planfile, journalfile, confirm):
    if confirm != "CUTOVER":
        raise MigrationError("Use --confirm CUTOVER for registry changes")
    if Path(journalfile).exists():
        raise MigrationError("Existing journal; inspect or rollback before another cutover")
    es, _, states = ha.inventory()
    mappings = validate_mappings(load_json(planfile), es, states)
    occupied = {e["entity_id"] for e in es}
    by_id = {e["entity_id"]: e for e in es}
    journal = {"schema": SCHEMA, "status": "prepared", "source": "JNS Tuya Freedom",
               "mappings": [{**x, "backup": unique_backup(x["cloud"], occupied),
                             "cloud_metadata": metadata_snapshot(by_id[x["cloud"]]),
                             "local_metadata": metadata_snapshot(by_id[x["local"]])}
                            for x in mappings]}
    secure_write(journalfile, journal)
    try:
        for pair in journal["mappings"]:
            ha.call("config/entity_registry/update",
                    entity_id=pair["cloud"], new_entity_id=pair["backup"])
            ha.call("config/entity_registry/update",
                    entity_id=pair["local"], new_entity_id=pair["cloud"])
            apply_metadata(ha, pair["cloud"], pair.get("cloud_metadata", {}))
        journal["status"] = "local_entity_ids_active_cloud_entries_retained"
        secure_write(journalfile, journal)
    except Exception:
        journal["status"] = "cutover_failed_rollback_attempted"
        try:
            rollback_operations(ha, journal)
            journal["status"] = "rolled_back"
        finally:
            secure_write(journalfile, journal)
        raise


def user_rollback(ha, journalfile, confirm):
    if confirm != "ROLLBACK":
        raise MigrationError("Use --confirm ROLLBACK")
    journal = load_json(journalfile)
    if journal.get("schema") != SCHEMA or journal.get("status") == "rolled_back":
        raise MigrationError("Journal invalid or already rolled back")
    rollback_operations(ha, journal)
    journal["status"] = "rolled_back"
    secure_write(journalfile, journal)


def main():
    parser = argparse.ArgumentParser(description="Cloud-to-local Tuya migration, HA WebSocket based")
    parser.add_argument("action", choices=["audit", "plan", "cutover", "rollback", "verify"])
    parser.add_argument("--url", default="http://homeassistant.local:8123",
                        help="Home Assistant URL (any installation)")
    parser.add_argument("--token-env", default="HA_TOKEN",
                        help="Environment variable holding HA long-lived admin token")
    parser.add_argument("--inventory", default="tuya-freedom-private-inventory.json")
    parser.add_argument("--plan", default="tuya-freedom-private-plan.json")
    parser.add_argument("--journal", default="tuya-freedom-private-journal.json")
    parser.add_argument("--confirm", default="")
    args = parser.parse_args()
    token = os.environ.get(args.token_env, "")
    if not token:
        raise MigrationError("HA token environment variable is missing")
    ha = HA(args.url, token)
    try:
        if args.action == "audit":
            data = snapshot(ha)
            secure_write(args.inventory, data)
            print("PRIVATE_AUDIT_SAVED", args.inventory,
                  "cloud_entities", len(data["cloud"]), "local_entities", len(data["local"]),
                  "preexisting_local_tuya_entities", len(data["preexisting_local"]))
        elif args.action == "plan":
            data = snapshot(ha)
            secure_write(args.inventory, data)
            plan = propose(data)
            secure_write(args.plan, plan)
            print("PRIVATE_PLAN_SAVED", args.plan, "name_hints", len(plan["mappings"]),
                  "approved", 0)
        elif args.action == "cutover":
            cutover(ha, args.plan, args.journal, args.confirm)
            print("LOCAL_ENTITY_IDS_ACTIVE; CLOUD_CONFIG_UNCHANGED")
        elif args.action == "rollback":
            user_rollback(ha, args.journal, args.confirm)
            print("ROLLBACK_COMPLETED")
        elif args.action == "verify":
            es, _, states = ha.inventory()
            if not Path(args.journal).exists():
                raise MigrationError("No cutover journal")
            journal = load_json(args.journal)
            results = []
            by_id = {x["entity_id"]: x for x in es}
            for x in journal["mappings"]:
                eid = x["cloud"]
                results.append(by_id.get(eid, {}).get("platform") in LOCAL
                               and states.get(eid) not in BAD_STATES
                               and eid in states)
            print("LOCAL_ENTITIES_RESPONDING", sum(results), "/", len(results))
            print("NOTE: online state check is NOT proof of operation with WAN and Tuya DNS blocked.")
    finally:
        ha.close()


if __name__ == "__main__":
    try:
        main()
    except (MigrationError, OSError, ValueError, ImportError) as exc:
        print("BLOCKED:", type(exc).__name__, str(exc), file=sys.stderr)
        sys.exit(2)
