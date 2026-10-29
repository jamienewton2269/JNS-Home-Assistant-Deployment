#!/usr/bin/env python3
"""Offline-only release checks: no SSH, Supervisor calls or device operations."""
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).parent
APP = ROOT / "ha905_security_esphome_handover_app"

class SecurityV012ReleaseTests(unittest.TestCase):
    def test_single_reviewed_app_version_everywhere(self):
        manifest = (APP / "config.yaml").read_text()
        install = (ROOT / "ha905_security_esphome_install_stopped_guarded_20261028.py").read_text()
        enrol = (ROOT / "ha906_to_905_esphome_enrol_guarded_20261028.py").read_text()
        stop = (ROOT / "ha_security_vm906_guarded_stop_20261028.py").read_text()
        self.assertIn('version: "0.1.2"', manifest)
        self.assertIn('pre.get("version")=="0.1.2"', install)
        self.assertIn('info.get("version")!="0.1.2"', install)
        self.assertIn('original.get("version")!="0.1.2"', enrol)
        self.assertIn('info.get("version")=="0.1.2"', stop)
        self.assertNotIn('original.get("version")!="0.1.1"', enrol)
        self.assertNotIn('info.get("version")=="0.1.1"', stop)
    def test_actual_installed_inventory_and_stopped_state_required(self):
        install = (ROOT / "ha905_security_esphome_install_stopped_guarded_20261028.py").read_text()
        enrol = (ROOT / "ha906_to_905_esphome_enrol_guarded_20261028.py").read_text()
        stop = (ROOT / "ha_security_vm906_guarded_stop_20261028.py").read_text()
        self.assertIn('def app_installed():', install)
        self.assertIn('or not app_installed()', install)
        self.assertIn('original.get("state")!="stopped"', enrol)
        self.assertIn('info.get("state")=="stopped"', stop)
        self.assertIn('"ha","apps","list"', stop)
        self.assertIn('len(found)!=1', stop)
    def test_http_diagnostics_redacted_and_no_secret_logging(self):
        flow = (APP / "flow.py").read_text()
        enrol = (ROOT / "ha906_to_905_esphome_enrol_guarded_20261028.py").read_text()
        for diagnostic in ("HTTP_STATUS", "HTTP_PHASE"):
            self.assertIn('note("'+diagnostic+'"', flow)
            self.assertIn('"' + diagnostic + '"', enrol)
        self.assertIn('classify_safe_http_failure(logs)', enrol)
        self.assertNotIn('print(logs)', enrol)
        self.assertNotIn('print(credentials)', flow)
        self.assertNotIn('print(payload)', flow)
    def test_fail_closed_recovery_and_explicit_approval_retained(self):
        stop = (ROOT / "ha_security_vm906_guarded_stop_20261028.py").read_text()
        enrol = (ROOT / "ha906_to_905_esphome_enrol_guarded_20261028.py").read_text()
        operator = (ROOT / "ha906_to_905_exclusive_cutover_operator_20261028.py").read_text()
        recover = (ROOT / "ha906_nodec_auto_failback_20261028.py").read_text()
        self.assertIn('nodec_auto_recovery_not_armed', enrol)
        self.assertIn('exclusive_source_not_stopped', enrol)
        self.assertIn('nodea_fence_gated_recovery_timer_inactive', enrol)
        self.assertIn('nodec_failback_source_not_staged_exactly', stop)
        self.assertIn('JNS_ONSITE_OPERATOR_CONFIRMED', operator)
        self.assertIn('JNS_EMERGENCY_VM905_SUSPEND_APPROVED', operator)
        self.assertIn('qm","suspend","905"', recover)
        self.assertIn('target_fence_not_verified', recover)
        self.assertLess(recover.index('qm","suspend","905"'), recover.index('qm","start","906"'))
    def test_physical_acceptance_not_auto_granted(self):
        operator = (ROOT / "ha906_to_905_exclusive_cutover_operator_20261028.py").read_text()
        self.assertIn("awaiting_physical_approval", operator)
        self.assertNotIn("ha906_to_905_accept_operator_20261028.py\",", operator)

if __name__ == "__main__":
    unittest.main(verbosity=2)
