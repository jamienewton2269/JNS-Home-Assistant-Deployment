#!/usr/bin/env python3
"""Self-contained regression tests; do not connect to any Home Assistant system."""
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from tuya_freedom import (
    MigrationError, propose, validate_mappings, secure_write, cutover,
    rollback_operations,
)

def fake_entity(eid, platform):
    return {"entity_id": eid, "platform": platform, "name": "Living Room",
            "original_name": "Living Room", "disabled_by": None, "device_id": None}

class FakeHA:
    def __init__(self):
        self.es = {
            "switch.kitchen": fake_entity("switch.kitchen", "tuya"),
            "switch.kitchen_local": fake_entity("switch.kitchen_local", "tuya_local"),
        }
        self.states = {"switch.kitchen": "off", "switch.kitchen_local": "off"}
        self.calls = []

    def inventory(self):
        return list(self.es.values()), [], dict(self.states)

    def call(self, method, **kw):
        assert method == "config/entity_registry/update"
        old, new = kw["entity_id"], kw["new_entity_id"]
        assert new not in self.es
        obj = self.es.pop(old)
        obj["entity_id"] = new
        self.es[new] = obj
        if old in self.states:
            self.states[new] = self.states.pop(old)
        self.calls.append((old, new))


class FreedomTests(unittest.TestCase):
    def test_plan_never_autoapproves(self):
        cloud = [dict(fake_entity("switch.kitchen", "tuya"), domain="switch", friendly_name="Kitchen", device_name="Kitchen")]
        local = [dict(fake_entity("switch.kitchen_local", "tuya_local"), domain="switch", friendly_name="Kitchen", device_name="Kitchen")]
        p = propose({"cloud": cloud, "local": local})
        self.assertEqual(len(p["mappings"]), 1)
        self.assertFalse(p["mappings"][0]["approved"])

    def test_refuse_unapproved_or_unavailable(self):
        ha = FakeHA()
        es, _, states = ha.inventory()
        p = {"schema": 1, "mappings": [{"cloud": "switch.kitchen", "local": "switch.kitchen_local", "approved": False}]}
        with self.assertRaises(MigrationError):
            validate_mappings(p, es, states)
        p["mappings"][0]["approved"] = True
        states["switch.kitchen_local"] = "unavailable"
        with self.assertRaises(MigrationError):
            validate_mappings(p, es, states)

    def test_cutover_and_rollback(self):
        ha = FakeHA()
        with tempfile.TemporaryDirectory() as directory:
            plan = Path(directory) / "plan.json"
            journal = Path(directory) / "journal.json"
            secure_write(plan, {"schema": 1, "mappings": [
                {"cloud": "switch.kitchen", "local": "switch.kitchen_local", "approved": True}
            ]})
            with self.assertRaises(MigrationError):
                cutover(ha, plan, journal, "NO")
            cutover(ha, plan, journal, "CUTOVER")
            self.assertEqual(ha.es["switch.kitchen"]["platform"], "tuya_local")
            rec = json.loads(journal.read_text())
            self.assertEqual(rec["status"], "local_entity_ids_active_cloud_entries_retained")
            rollback_operations(ha, rec)
            self.assertEqual(ha.es["switch.kitchen"]["platform"], "tuya")
            self.assertEqual(ha.es["switch.kitchen_local"]["platform"], "tuya_local")

    def test_private_file_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "inventory.json"
            secure_write(file, {"ok": True})
            self.assertEqual(stat.S_IMODE(file.stat().st_mode), 0o600)


if __name__ == "__main__":
    unittest.main()
