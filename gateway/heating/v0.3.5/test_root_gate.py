"""Fail-closed audit gate tests (synthetic temp files only)."""
import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
SPEC=importlib.util.spec_from_file_location("jns_heating_root_gate",Path(__file__).with_name("nodeb_root_gate.py"))
G=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(G)
class GateTest(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.approval=Path(self.temp.name)/"approval.json"
        self.patch_path=patch.object(G,"APPROVAL",self.approval)
        self.patch_path.start()
        self.addCleanup(self.patch_path.stop)
        self.patch_owner=patch.object(G,"owned_by_root",return_value=True)
        self.patch_owner.start()
        self.addCleanup(self.patch_owner.stop)
        self.patch_root=patch.object(G.os,"geteuid",return_value=0)
        self.patch_root.start()
        self.addCleanup(self.patch_root.stop)
    def write(self, **changes):
        fields={"stage_id":G.STAGE,"candidate_sha256":G.EXPECTED_CANDIDATE_SHA,
                "intent":"assess_only","operator_window":"local-review"}
        fields.update(changes)
        self.approval.write_text(json.dumps(fields))
        self.approval.chmod(0o600)
    def test_no_approval_blocks(self):
        with self.assertRaisesRegex(RuntimeError,"absent"):G.approval_audit()
    def test_exact_approval_allows_audit_only(self):
        self.write()
        self.assertEqual(G.approval_audit()["approval"],"assess_only")
    def test_wrong_candidate_blocks(self):
        self.write(candidate_sha256="0"*64)
        with self.assertRaisesRegex(RuntimeError,"mismatch"):G.approval_audit()
    def test_explicit_commit_intent_blocks(self):
        self.write(intent="commit")
        with self.assertRaisesRegex(RuntimeError,"not yet authorised"):G.approval_audit()
    def test_world_readable_approval_blocks(self):
        self.write()
        self.approval.chmod(0o644)
        with self.assertRaisesRegex(RuntimeError,"permissions"):G.approval_audit()
    def test_no_root_blocks(self):
        self.write()
        with patch.object(G.os,"geteuid",return_value=1000):
            with self.assertRaisesRegex(RuntimeError,"root"):G.approval_audit()
    def test_unknown_fields_block(self):
        self.write(extra_command="unexpected")
        with self.assertRaisesRegex(RuntimeError,"unknown approval fields"):G.approval_audit()
if __name__=="__main__":
    unittest.main()
