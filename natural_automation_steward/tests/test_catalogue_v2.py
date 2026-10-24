from __future__ import annotations
import json
import subprocess
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"tools"))
import sync_repair_catalogue_v2 as corpus


class CatalogueTests(unittest.TestCase):
    def _fixture(self,root):
        (root/".github/workflows").mkdir(parents=True)
        (root/"gateway/lux_manual_override").mkdir(parents=True)
        (root/"gateway/lux_manual_override/repair.py").write_text(
            '"""Fix manual OFF so the lux controller respects intentional light-off."""\n'
            'import os\n'
            'def repair():\n'
            '  assert os.path.exists("/config/automations.yaml")\n'
        )
        (root/".github/workflows/repair.yml").write_text(
            'name: Repair Lux Controller\n'
            'jobs:\n  deploy:\n    steps:\n      - run: python3 gateway/lux_manual_override/repair.py\n'
        )
        subprocess.run(["git","init","-q"],cwd=root,check=True)
        subprocess.run(["git","-c","user.name=Test","-c","user.email=test@example.invalid",
            "commit","--allow-empty","-qm","fixture"],cwd=root,check=True)
    def test_complete_static_dossiers_and_linked_workflow(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self._fixture(root)
            record=next(r for r in corpus.build(root)["records"] if r["source_path"].endswith("repair.py"))
            self.assertIn("Fix manual OFF",record["why"])
            self.assertEqual(record["evidence"]["purpose_provenance"],"python_module_docstring")
            self.assertEqual(record["evidence"]["execution_result"],"not_established_from_repository_source")
            self.assertEqual(record["safety_class"],"manual_review")
            self.assertEqual(record["evidence"]["workflow_references"],[".github/workflows/repair.yml"])
            self.assertEqual(record["artifact"]["content"].count("Fix manual OFF"),1)
    def test_filename_only_does_not_invent_prior_outcomes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/"management_bridge").mkdir()
            p=root/"management_bridge"/"repair_example.sh"
            p.write_text("#!/bin/bash\ntrue\n")
            rec=corpus.explain(root,p,{})
            self.assertIn("Undocumented purpose",rec["why"])
            self.assertEqual(rec["evidence"]["execution_result"],"not_established_from_repository_source")
            self.assertFalse(rec["evidence"]["observed_production_success"])
            self.assertEqual(rec["portable"],False)
    def test_credential_suspect_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/"gateway").mkdir()
            p=root/"gateway"/"example.py"
            p.write_text('password="ABCDEFGHIJKLMNOPQRSTUV1234567890"\n')
            with self.assertRaises(RuntimeError):
                corpus.build(root)
    def test_import_preserves_facts_old_knowledge_and_feedback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"repo";root.mkdir();self._fixture(root)
            seed=Path(tmp)/"seed.json"
            payload=corpus.build(root);corpus.export(payload,seed)
            dbpath=Path(tmp)/"steward.db"
            conn=sqlite3.connect(dbpath)
            conn.executescript("""
            CREATE TABLE repairs(
              id TEXT PRIMARY KEY,fingerprint TEXT UNIQUE,title TEXT,subsystem TEXT,
              recipe_json TEXT,confidence REAL,successful_runs INT DEFAULT 0,
              failed_runs INT DEFAULT 0,portable INTEGER,updated_at REAL);
            CREATE TABLE facts(namespace TEXT,key TEXT,value_json TEXT,updated_at REAL,
              PRIMARY KEY(namespace,key));
            CREATE VIRTUAL TABLE repair_search USING fts5(
              repair_id UNINDEXED,title,subsystem,problem,symptoms,diagnosis,steps);
            """)
            conn.execute("INSERT INTO repairs VALUES(?,?,?,?,?,?,?,?,?,?)",
                ("original","orig_fp","Original", "zigbee",'{"title":"Original"}',0.7,4,1,0,1))
            conn.execute("INSERT INTO facts VALUES('site_knowledge','manifest','{}',1)")
            conn.commit();conn.close()
            report=corpus.import_catalogue(seed,dbpath)
            self.assertEqual(report["imported"],2)
            self.assertEqual(report["repairs_before"],1)
            conn=sqlite3.connect(dbpath)
            self.assertEqual(conn.execute("SELECT successful_runs,failed_runs FROM repairs WHERE id='original'").fetchone(),(4,1))
            self.assertEqual(conn.execute("SELECT value_json FROM facts WHERE namespace='site_knowledge'").fetchone()[0],"{}")
            self.assertEqual(conn.execute("SELECT count(*) FROM repairs").fetchone()[0],3)
            conn.close()
            report=corpus.import_catalogue(seed,dbpath)
            self.assertEqual(report["repairs_after"],3)
            self.assertTrue(Path(report["backup"]).exists())


if __name__=="__main__":unittest.main()
