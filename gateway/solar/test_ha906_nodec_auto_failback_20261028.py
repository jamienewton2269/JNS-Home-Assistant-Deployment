#!/usr/bin/env python3
"""Simulated high-risk recovery outcomes; NEVER executes a real SSH command."""
import importlib.util
import pathlib
import unittest
from unittest.mock import patch

P=pathlib.Path(__file__).parent/"ha906_nodec_auto_failback_20261028.py"
spec=importlib.util.spec_from_file_location("safe_failback",P)
f=importlib.util.module_from_spec(spec)
spec.loader.exec_module(f)

class FailureRollbackTests(unittest.TestCase):
    def scenario(self,source="stopped",target="running",count=0,suspend_ok=True,accepted=False):
        calls=[]
        x={"source":source,"target":target}
        def status(node,vm):
            return x["source"] if node=="nodea" else x["target"]
        def fake_ssh(node,argv,timeout=30):
            cmd=argv[:]
            calls.append((node,cmd))
            if cmd[:3]==["qm","suspend","905"]:
                if suspend_ok:x["target"]="suspended"
                return type("Result",(),{"returncode":0 if suspend_ok else 1,"stdout":""})()
            if cmd[:3]==["qm","start","906"]:
                x["source"]="running"
                return type("Result",(),{"returncode":0,"stdout":""})()
            if cmd and cmd[0]=="python3":
                return type("Result",(),{"returncode":0,"stdout":"JNS_NODEA_RECOVERY_ATTESTED=yes"})()
            raise AssertionError(str(cmd))
        with patch.object(f,"nodea_done",lambda:accepted),\
             patch.object(f,"verified_source",lambda:True),\
             patch.object(f,"verified_target",lambda:True),\
             patch.object(f,"status",status),\
             patch.object(f,"active_target_count",lambda:count),\
             patch.object(f,"ssh",fake_ssh):
            rc=f.restore()
        return rc,calls,x
    def test_no_recovery_if_source_running(self):
        rc,calls,x=self.scenario(source="running")
        self.assertEqual(rc,0);self.assertEqual(calls,[])
    def test_no_recovery_after_acceptance(self):
        rc,calls,x=self.scenario(accepted=True)
        self.assertEqual(rc,0);self.assertEqual(calls,[])
    def test_pending_flow_with_no_registered_entry_still_fences_target(self):
        rc,calls,x=self.scenario(count=0)
        self.assertEqual(rc,0)
        self.assertEqual(x["target"],"suspended")
        self.assertTrue(any(args[:3]==["qm","suspend","905"] for _,args in calls))
        self.assertTrue(any(args[:3]==["qm","start","906"] for _,args in calls))
    def test_integrated_target_suspended_before_source_restart(self):
        rc,calls,x=self.scenario(count=1)
        self.assertEqual(rc,0);self.assertEqual(x["target"],"suspended")
        self.assertLess(next(i for i,(_,a) in enumerate(calls) if a[:3]==["qm","suspend","905"]),
                        next(i for i,(_,a) in enumerate(calls) if a[:3]==["qm","start","906"]))
    def test_failed_fence_never_promotes_source(self):
        rc,calls,x=self.scenario(count=1,suspend_ok=False)
        self.assertNotEqual(rc,0)
        self.assertFalse(any(a[:3]==["qm","start","906"] for _,a in calls))
    def test_unknown_target_integration_fences_before_restore(self):
        rc,calls,x=self.scenario(count=None,suspend_ok=True)
        self.assertEqual(rc,0);self.assertEqual(x["target"],"suspended")
if __name__=="__main__":unittest.main()
