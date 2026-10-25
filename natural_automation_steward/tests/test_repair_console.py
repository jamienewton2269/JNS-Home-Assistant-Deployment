"""Read-only Steward Repair Centre API and UI contracts."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from steward.repair_console import REPAIR_HTML,search_repair_catalogue

class RepairConsoleTests(unittest.TestCase):
    def test_query_is_sanitised_for_fts5(self):
        store=Mock()
        store.search_repairs.return_value=[]
        d=search_repair_catalogue(store,'lux OR "bedtime" [switch]',limit=5)
        self.assertEqual(d["fixes_applied"],0)
        query,limit=store.search_repairs.call_args.args
        self.assertEqual(query,'"lux" OR "or" OR "bedtime" OR "switch"')
        self.assertEqual(limit,5)
    def test_no_source_code_or_secrets_in_response(self):
        store=Mock()
        store.search_repairs.return_value=[{
            "title":"Test Repair","subsystem":"lighting",
            "why":"Demo", "how":"Inspect",
            "artifact":{"content":"secret_source_should_not_be_exposed"},
            "repair_steps":["Review only"],
            "verification_steps":["Read back state"],
            "rollback_steps":["Restore backup"],
            "source_path":"gateway/safe.py",
            "evidence":{"execution_result":"not_established_from_repository_source"},
        }]
        d=search_repair_catalogue(store,"lux")
        self.assertEqual(d["execution_authority"],"none")
        self.assertEqual(len(d["results"]),1)
        self.assertNotIn("secret_source_should_not_be_exposed",json.dumps(d))
        self.assertFalse(d["results"][0]["executable_from_interface"])
    def test_malformed_search_is_rejected(self):
        store=Mock()
        with self.assertRaises(ValueError):search_repair_catalogue(store,"x")
        with self.assertRaises(ValueError):search_repair_catalogue(store,"a"*241)
        store.search_repairs.assert_not_called()
    def test_page_safe_nonexecuting_controls(self):
        self.assertIn("Steward Repair Centre",REPAIR_HTML)
        self.assertIn("Find relevant repairs",REPAIR_HTML)
        self.assertIn("Copy assisted repair request",REPAIR_HTML)
        self.assertIn("/api/steward/repair-search",REPAIR_HTML)
        self.assertNotIn("onclick=\"apply",REPAIR_HTML.lower())
        self.assertNotIn("post('/api/apply",REPAIR_HTML)
    def test_route_exists_and_is_lan_gated(self):
        source=(Path(__file__).resolve().parents[1]/"src/natural_automation.py").read_text()
        self.assertIn('if path=="/steward/repairs":',source)
        self.assertIn('if path=="/api/steward/repair-search":',source)
        self.assertIn("if not admin_allowed(self)",source)
        self.assertIn("search_repair_catalogue(STEWARD",source)

if __name__=="__main__":
    unittest.main()
