"""Synthetic VM905 v0.3.6 file transaction tests. Never touches production."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import importlib.util,hashlib,json,unittest

ROOT=Path(__file__).parent
spec=importlib.util.spec_from_file_location("tx036",ROOT/"bathroom_v036_transaction.py")
T=importlib.util.module_from_spec(spec)
spec.loader.exec_module(T)

class Transaction36Test(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.comp=self.root/"custom_components"/"jns_heating_zones"
        self.comp.mkdir(parents=True)
        self.storage=self.root/".storage"
        self.storage.mkdir()
        self.baselines={}
        for name in ("coordinator.py","sensor.py","thermal.py","__init__.py","config_flow.py","const.py"):
            blob=b"fake "+name.encode()
            (self.comp/name).write_bytes(blob)
            self.baselines[name]=hashlib.sha256(blob).hexdigest()
        self.manifest=b'{"domain":"jns_heating_zones","version":"0.3.4","name":"Heating"}\n'
        (self.comp/"manifest.json").write_bytes(self.manifest)
        (self.storage/"jns_heating_zone_synthetic").write_text(json.dumps({
            "version":1,"data":{"samples":[{"at":"2026-10-26T12:00:00+00:00",
                           "indoor":20,"outdoor":10,"duty":0,"valid":True}]}}))
        self.history=(self.storage/"jns_heating_zone_synthetic").read_bytes()
        self.candidate={}
        for n,file in (("coordinator.py","bathroom_extension/coordinator.py"),
                       ("sensor.py","bathroom_extension/sensor.py"),
                       ("thermal.py","thermal.py"),
                       ("bathroom_reference.py","bathroom_reference.py"),
                       ("bathroom_runtime.py","bathroom_runtime.py")):
            self.candidate[n]=(ROOT/file).read_bytes()
        self.candidate["manifest.json"]=T.candidate_manifest(self.manifest)
        p=patch.object(T,"BASELINE",self.baselines)
        p.start();self.addCleanup(p.stop)

    def test_source_fingerprint_blocks_changed_live_coordinator(self):
        (self.comp/"coordinator.py").write_bytes(b"newer")
        with self.assertRaisesRegex(T.Blocked,"fingerprint"):
            T.snapshot(self.root,self.candidate)

    def test_source_fingerprint_blocks_existing_bathroom_module(self):
        (self.comp/"bathroom_runtime.py").write_text("already installed")
        with self.assertRaisesRegex(T.Blocked,"already exists"):
            T.snapshot(self.root,self.candidate)

    def test_private_staging_preserves_running_ha(self):
        state=T.stage(self.root,self.candidate)
        self.assertEqual(state["state"],"staged")
        self.assertFalse(state["new_integrations_active"])
        self.assertEqual((self.comp/"manifest.json").read_bytes(),self.manifest)
        self.assertEqual((self.storage/"jns_heating_zone_synthetic").read_bytes(),self.history)
        self.assertEqual(T.verify(self.root,state["stage_id"])["state"],"staged")
        d=self.root/T.ROOT_BACKUPS/state["stage_id"]
        self.assertFalse(d.stat().st_mode&0o077)
        for p in (d/"original").iterdir():
            self.assertFalse(p.stat().st_mode&0o077)

    def test_commit_guard_does_not_accept_unapproved(self):
        stage=T.stage(self.root,self.candidate)
        with self.assertRaisesRegex(T.Blocked,"permit"):
            T.apply(self.root,stage["stage_id"])
        self.assertEqual((self.comp/"manifest.json").read_bytes(),self.manifest)

    def test_controlled_apply_verify_and_restore(self):
        stage=T.stage(self.root,self.candidate)
        applied=T.apply(self.root,stage["stage_id"],approved=True)
        self.assertTrue(applied["restart_required"])
        self.assertFalse(applied["successful_activation"])
        self.assertEqual(json.loads((self.comp/"manifest.json").read_text())["version"],"0.3.6")
        self.assertTrue((self.comp/"bathroom_runtime.py").exists())
        self.assertEqual(T.verify(self.root,stage["stage_id"])["state"],"applied_pending_core_restart")
        rolled=T.rollback(self.root,stage["stage_id"],approved=True)
        self.assertEqual(rolled["state"],"rolled_back")
        self.assertEqual((self.comp/"manifest.json").read_bytes(),self.manifest)
        self.assertFalse((self.comp/"bathroom_runtime.py").exists())
        self.assertEqual((self.storage/"jns_heating_zone_synthetic").read_bytes(),self.history)

    def test_rollback_refuses_concurrent_edits(self):
        stage=T.stage(self.root,self.candidate)
        T.apply(self.root,stage["stage_id"],approved=True)
        (self.comp/"coordinator.py").write_bytes(b"new unrelated change")
        with self.assertRaisesRegex(T.Blocked,"later source changes"):
            T.rollback(self.root,stage["stage_id"],approved=True)

    def test_stage_rejects_symlink(self):
        (self.comp/"coordinator.py").unlink()
        (self.root/"external.py").write_bytes(b"fake coordinator.py")
        (self.comp/"coordinator.py").symlink_to(self.root/"external.py")
        with self.assertRaisesRegex(T.Blocked,"symlink"):
            T.snapshot(self.root,self.candidate)

    def test_live_legacy_storage_can_grow_and_never_restores_old_copy(self):
        stage=T.stage(self.root,self.candidate)
        p=self.storage/"jns_heating_zone_synthetic"
        original=json.loads(p.read_text())
        original["data"]["samples"].append({"at":"2026-10-26T12:05:00+00:00","indoor":20,
                       "outdoor":10,"duty":0,"valid":True})
        p.write_text(json.dumps(original))
        T.apply(self.root,stage["stage_id"],approved=True)
        T.rollback(self.root,stage["stage_id"],approved=True)
        self.assertEqual(len(json.loads(p.read_text())["data"]["samples"]),2)

    def test_invalid_candidate_rejected(self):
        m=dict(self.candidate)
        m["manifest.json"]=self.manifest
        with self.assertRaisesRegex(T.Blocked,"candidate manifest"):
            T.snapshot(self.root,m)

if __name__=="__main__":
    unittest.main()
