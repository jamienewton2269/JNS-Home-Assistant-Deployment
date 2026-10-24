"""Offline guarded installer tests, using synthetic HA fixture files only."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

SPEC=importlib.util.spec_from_file_location("jns_heating_transaction",Path(__file__).with_name("transaction.py"))
T=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(T)
CANDIDATE=Path(__file__).with_name("thermal.py").read_bytes()


class TransactionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory(prefix="jns-heat-test-")
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.comp=self.root/"custom_components/jns_heating_zones"
        self.store=self.root/".storage"
        self.comp.mkdir(parents=True)
        self.store.mkdir()
        self.original=b"# Fake old thermal learner, no real private data\n"
        (self.comp/"thermal.py").write_bytes(self.original)
        self.manifest=b'{"domain":"jns_heating_zones","version":"0.3.4","name":"Test Heating"}\n'
        (self.comp/"manifest.json").write_bytes(self.manifest)
        names=("coordinator.py","sensor.py","__init__.py")
        self.unchanged={name:hashlib.sha256(name.encode()).hexdigest() for name in names}
        for name in names:
            (self.comp/name).write_bytes(name.encode())
        self.patcher=patch.multiple(T,OLD_THERMAL_SHA=hashlib.sha256(self.original).hexdigest(),
                                    EXPECTED_UNCHANGED=self.unchanged)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.saved={
            "version":1,"minor_version":1,
            "key":"synthetic-zone-only","data":{
                "samples":[{"at":"2026-10-24T09:00:00+00:00",
                            "indoor":20.0,"outdoor":9.0,"duty":0.0,"valid":True}],
                "watch":{"active":False}
            }
        }
        self.saved_path=self.store/"jns_heating_zone_test"
        self.saved_path.write_text(json.dumps(self.saved))
        registry={"data":{"entities":[{"entity_id":x} for x in T.EXPECTED_ENTITIES]}}
        (self.store/"core.entity_registry").write_text(json.dumps(registry))

    def test_preflight_accepts_valid_fixture_and_rejects_wrong_hash(self):
        self.assertIn("stores",T.inventory(self.root,CANDIDATE))
        (self.comp/"thermal.py").write_text("# unexpected modification")
        with self.assertRaisesRegex(T.GuardError,"fingerprint"):
            T.inventory(self.root,CANDIDATE)

    def test_stage_private_backup_does_not_touch_active_files(self):
        old_data=self.saved_path.read_bytes()
        stage=T.stage(self.root,CANDIDATE)
        folder=self.root/T.SNAPSHOT/stage["stage_id"]
        self.assertEqual(stage["state"],"staged")
        self.assertTrue(stage["runtime_untouched"])
        self.assertEqual((self.comp/"thermal.py").read_bytes(),self.original)
        self.assertEqual((self.comp/"manifest.json").read_bytes(),self.manifest)
        self.assertEqual(self.saved_path.read_bytes(),old_data)
        self.assertEqual((folder/"stores"/self.saved_path.name).read_bytes(),old_data)
        for directory in (self.root/T.SNAPSHOT,folder,folder/"stores",folder/"original"):
            self.assertEqual(directory.stat().st_mode&0o077,0)
        for file in (folder/"candidate.py",folder/"state.json",folder/"stores"/self.saved_path.name):
            self.assertEqual(file.stat().st_mode&0o077,0)
        self.assertEqual(T.verify(self.root,stage["stage_id"])["state"],"staged")

    def test_commit_requires_gate_and_rolls_back_without_resetting_learning(self):
        stage=T.stage(self.root,CANDIDATE)
        with self.assertRaisesRegex(T.GuardError,"authorised"):
            T.commit(self.root,stage["stage_id"])
        self.saved["data"]["samples"].append({
           "at":"2026-10-24T09:05:00+00:00",
           "indoor":20.0,"outdoor":9.0,"duty":0.0,"valid":True})
        self.saved_path.write_text(json.dumps(self.saved))
        state=T.commit(self.root,stage["stage_id"],approved=True)
        self.assertEqual(state["state"],"applied_pending_runtime_verification")
        self.assertEqual((self.comp/"thermal.py").read_bytes(),CANDIDATE)
        self.assertEqual(json.loads((self.comp/"manifest.json").read_text())["version"],"0.3.5")
        self.assertEqual(T.verify(self.root,stage["stage_id"])["runtime_reload"],False)
        before=self.saved_path.read_bytes()
        rolled=T.rollback(self.root,stage["stage_id"])
        self.assertTrue(rolled["learning_store_preserved"])
        self.assertEqual((self.comp/"thermal.py").read_bytes(),self.original)
        self.assertEqual((self.comp/"manifest.json").read_bytes(),self.manifest)
        self.assertEqual(self.saved_path.read_bytes(),before)

    def test_stage_rejects_missing_entity_or_changed_source(self):
        (self.store/"core.entity_registry").write_text('{"data":{"entities":[]}}')
        with self.assertRaisesRegex(T.GuardError,"not registered"):
            T.stage(self.root,CANDIDATE)
        self.assertEqual((self.comp/"thermal.py").read_bytes(),self.original)

    def test_stage_detects_symlink_source(self):
        real=self.root/"other"
        real.write_bytes(self.original)
        (self.comp/"thermal.py").unlink()
        (self.comp/"thermal.py").symlink_to(real)
        with self.assertRaisesRegex(T.GuardError,"symlink"):
            T.inventory(self.root,CANDIDATE)

    def test_commit_denies_concurrent_changes(self):
        staged=T.stage(self.root,CANDIDATE)
        (self.comp/"manifest.json").write_text('{"version":"9.9"}')
        with self.assertRaisesRegex(T.GuardError,"manifest changed"):
            T.commit(self.root,staged["stage_id"],approved=True)
        self.assertEqual((self.comp/"thermal.py").read_bytes(),self.original)

    def test_rollback_denies_overwriting_newer_work(self):
        staged=T.stage(self.root,CANDIDATE)
        T.commit(self.root,staged["stage_id"],approved=True)
        (self.comp/"thermal.py").write_text("# newer release")
        with self.assertRaisesRegex(T.GuardError,"newer thermal"):
            T.rollback(self.root,staged["stage_id"])
        self.assertEqual((self.comp/"thermal.py").read_text(),"# newer release")

    def test_apply_exception_restores_original_files(self):
        staged=T.stage(self.root,CANDIDATE)
        actual=T.atomic
        def fail_manifest(path,*args,**kw):
            if Path(path).name=="manifest.json" and Path(path).parent==self.comp:
                raise OSError("mock power failure on second write")
            return actual(path,*args,**kw)
        with patch.object(T,"atomic",side_effect=fail_manifest):
            with self.assertRaises(OSError):
                T.commit(self.root,staged["stage_id"],approved=True)
        self.assertEqual((self.comp/"thermal.py").read_bytes(),self.original)
        self.assertEqual((self.comp/"manifest.json").read_bytes(),self.manifest)
        self.assertEqual(T.verify(self.root,staged["stage_id"])["state"],"staged")


if __name__=="__main__":
    unittest.main()
