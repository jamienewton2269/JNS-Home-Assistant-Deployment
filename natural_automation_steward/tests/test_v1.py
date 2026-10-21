import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
TOOLS = ROOT / "tools"
sys.path.insert(0, str(SRC))
sys.path.insert(0, str(TOOLS))

from steward.proposals import build_automation_proposal, ProposalStore
from steward.target import parse_qm_list
from steward.store import StewardStore
from steward.repair_capture import capture
import seed_repairs


class ProposalTests(unittest.TestCase):
    def test_24_hour_duration_proposal(self):
        p = build_automation_proposal(
            "turn on the kitchen worktop light at 16:35 for 5 mins",
            "light.kitchen_worktop_downlight",
            "Kitchen Worktop Light",
        )
        self.assertIsNotNone(p)
        self.assertEqual(p.automation["trigger"][0]["at"], "16:35:00")
        self.assertEqual(p.automation["action"][1]["delay"], {"minutes": 5})
        self.assertEqual(
            p.automation["action"][0]["target"]["entity_id"],
            "light.kitchen_worktop_downlight",
        )

    def test_12_hour_clock(self):
        p = build_automation_proposal(
            "turn on hall light at 4:35pm for 10 minutes",
            "light.hall",
            "Hall",
        )
        self.assertEqual(p.automation["trigger"][0]["at"], "16:35:00")

    def test_ambiguous_schedule_has_no_proposal(self):
        self.assertIsNone(
            build_automation_proposal(
                "turn on the hall light at bedtime",
                "light.hall",
                "Hall",
            )
        )

    def test_proposal_store_expires(self):
        store = ProposalStore(ttl_seconds=-1)
        p = build_automation_proposal(
            "turn on hall light at 16:35 for 1 minute",
            "light.hall",
        )
        store.put(p)
        self.assertIsNone(store.get(p.proposal_id))


class TargetTests(unittest.TestCase):
    def test_parse_qm_list(self):
        rows = parse_qm_list(
            " VMID NAME STATUS MEM(MB) BOOTDISK(GB) PID\n"
            " 905 ha-s2-general running 2048 32.00 1234\n"
            " 906 ha-security stopped 2048 32.00 0\n"
        )
        self.assertEqual(rows[0][:2], (905, "ha-s2-general"))
        self.assertEqual(rows[1][:2], (906, "ha-security"))


class StoreTests(unittest.TestCase):
    def test_capture_is_searchable_and_dedupes(self):
        with tempfile.TemporaryDirectory() as td:
            store = StewardStore(Path(td) / "steward.db")
            recipe = {
                "title": "Zigbee coordinator recovery",
                "subsystem": "zigbee",
                "problem": "Coordinator unavailable",
                "diagnosis": "Adapter path changed",
                "repair_steps": ["Resolve stable hardware ID"],
                "verification_steps": ["Confirm Zigbee2MQTT is healthy"],
                "rollback_steps": ["Restore previous adapter path"],
                "confidence": 0.7,
            }
            rid1 = capture(store, recipe, success=True)
            rid2 = capture(store, recipe, success=True)
            self.assertEqual(rid1, rid2)
            self.assertEqual(store.status()["repairs"], 1)
            hits = store.search_repairs("coordinator")
            self.assertEqual(len(hits), 1)

    def test_seed_script_runs_from_installed_layout(self):
        import shutil
        import subprocess
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            installed = td / "natural-automation"
            (installed / "tools").mkdir(parents=True)
            shutil.copy2(ROOT / "tools" / "seed_repairs.py", installed / "tools" / "seed_repairs.py")
            shutil.copytree(SRC / "steward", installed / "steward")

            seed = td / "seed.json"
            seed.write_text(json.dumps({
                "schema": "steward-repair-seed-v1",
                "records": [{
                    "id": "seed-one",
                    "title": "Installed layout test",
                    "subsystem": "home_assistant",
                    "problem": "test",
                    "diagnosis": "",
                    "repair_steps": [],
                    "verification_steps": [],
                    "rollback_steps": [],
                    "confidence": 0.5,
                    "portable": False,
                    "safety_class": "manual_review",
                    "source_path": "test/example.sh",
                    "source_sha256": "abc",
                }]
            }))
            db = td / "steward.db"
            p = subprocess.run(
                [
                    sys.executable,
                    str(installed / "tools" / "seed_repairs.py"),
                    "--db", str(db),
                    "--import-json", str(seed),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(p.returncode, 0, p.stderr)
            store = StewardStore(db)
            self.assertEqual(store.status()["repairs"], 1)
    def test_historical_seed_is_manual_review(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "repo"
            (repo / "management_bridge").mkdir(parents=True)
            script = repo / "management_bridge" / "jns-zigbee-test.sh"
            script.write_text("#!/bin/sh\necho zigbee test\n")
            seed = Path(td) / "seed.json"
            count = seed_repairs.export_seed(repo, seed)
            self.assertEqual(count, 1)

            db = Path(td) / "steward.db"
            imported = seed_repairs.import_seed(db, seed)
            self.assertEqual(imported, 1)
            store = StewardStore(db)
            hits = store.search_repairs("zigbee")
            self.assertEqual(len(hits), 1)
            self.assertEqual(hits[0]["safety_class"], "manual_review")
            self.assertFalse(hits[0]["portable"])


class SourceContractTests(unittest.TestCase):
    def test_no_fixed_vmid_in_service(self):
        service = (ROOT / "systemd" / "natural-automation.service").read_text()
        self.assertNotIn("NA_VMID=", service)
        self.assertIn("NA_TARGET_ROLE=ha-general", service)

    def test_writer_targets_real_ha_automation_file(self):
        writer = (SRC / "steward" / "writer.py").read_text()
        self.assertIn("/config/automations.yaml", writer)
        self.assertNotIn("/config/natural_automation.yaml", writer)

    def test_apply_ui_and_proposal_id_contract_present(self):
        app = (SRC / "natural_automation.py").read_text()
        self.assertIn("Apply automation", app)
        self.assertIn("proposal_id", app)
        self.assertIn("TARGET_RESOLVER", app)
        self.assertNotIn("VMID=int(os.environ", app)


if __name__ == "__main__":
    unittest.main()
