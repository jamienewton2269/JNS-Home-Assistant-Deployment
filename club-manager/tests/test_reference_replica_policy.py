import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from reference_replica_policy import ExportPolicyError, make_reference_record, make_snapshot

class ReferencePolicyTests(unittest.TestCase):
    def test_explicit_publication_only(self):
        source = {"vessel_id": "v-1", "display_name": "Test Boat", "sail_number": "123"}
        with self.assertRaises(ExportPolicyError):
            make_reference_record(source, published=False, consented=True)
        with self.assertRaises(ExportPolicyError):
            make_reference_record(source, published=True, consented=False)
        self.assertEqual(make_reference_record(source, published=True, consented=True)["vessel_id"], "v-1")

    def test_no_personal_data(self):
        for field in ("email", "member_id", "crew_names", "bank", "unknown_field"):
            with self.subTest(field=field), self.assertRaises(ExportPolicyError):
                make_reference_record({"vessel_id":"v-1", "display_name":"Boat", field:"secret"},
                                      published=True, consented=True)

    def test_duplicate_and_stale_sequence_rejected(self):
        row = {"vessel_id": "v-1", "display_name": "Boat"}
        now = datetime.now(timezone.utc)
        with self.assertRaises(ExportPolicyError):
            make_snapshot([row, row], sequence=1, issued_at=now)
        with self.assertRaises(ExportPolicyError):
            make_snapshot([row], sequence=0, issued_at=now)

    def test_deterministic_order(self):
        now = datetime(2026, 11, 18, tzinfo=timezone.utc)
        rows = [{"vessel_id":"z", "display_name":"Z"}, {"vessel_id":"a", "display_name":"A"}]
        snapshot = make_snapshot(rows, sequence=2, issued_at=now)
        self.assertEqual([r["vessel_id"] for r in snapshot["vessels"]], ["a","z"])

if __name__ == "__main__":
    unittest.main()
