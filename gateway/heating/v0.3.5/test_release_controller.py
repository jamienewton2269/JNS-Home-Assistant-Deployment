"""Offline release-controller safety tests: no live VM/API calls."""
import contextlib
import importlib.util
import io
from pathlib import Path
from tempfile import TemporaryDirectory
import sys
import unittest
from unittest.mock import patch
SPEC=importlib.util.spec_from_file_location("jns_heating_release",Path(__file__).with_name("release_controller.py"))
M=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)

def states(call="off",action="idle",diagnostic=True):
    return {
       "binary_sensor.lyric_home_heating_heating_call":{"state":call},
       "climate.thermostat_thermostat":{"state":"heat","attributes":{"hvac_action":action}},
       "sensor.thermostat_thermostat_indoor_temperature":{"state":"20.0"},
       "sensor.lyric_home_heating_thermal_learning":{"state":"Learning: insufficient temperature variation",
          "attributes":{"valid_windows":28} if diagnostic else {}},
    }

class ReleaseSafetyTest(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory(prefix="jns-heat-controller-test-")
        self.addCleanup(self.temp.cleanup)
        patcher=patch.object(M,"LOCK_FILE",Path(self.temp.name)/"promotion.lock")
        patcher.start()
        self.addCleanup(patcher.stop)
        approval=patch.object(M,"consume_approval")
        approval.start()
        self.addCleanup(approval.stop)
    def test_cannot_reload_while_heating_active(self):
        with self.assertRaisesRegex(M.Blocked,"heating call active"):
            M.idle(states(call="on"))
        with self.assertRaisesRegex(M.Blocked,"thermostat actively"):
            M.idle(states(action="heating"))

    def test_idle_requires_numeric_sensor(self):
        with self.assertRaises(M.Blocked):
            M.idle(states() | {"sensor.thermostat_thermostat_indoor_temperature":{"state":"unknown"}})

    def test_version_diagnostics_required(self):
        with self.assertRaisesRegex(M.Blocked,"diagnostics"):
            M.is_candidate_live(states(diagnostic=False))

    def test_unauthorised_arguments_rejected(self):
        with patch.object(sys,"argv",["program","--restart"]),patch.object(M.os,"geteuid",return_value=0):
            with self.assertRaisesRegex(M.Blocked,"unknown requested operation"):
                M.run()

    def test_safe_preflight_no_write_or_reload(self):
        with patch.object(sys,"argv",["program","--preflight"]),\
             patch.object(M.os,"geteuid",return_value=0),\
             patch.object(M,"approval",return_value={"intent":"promote_v035"}),\
             patch.object(M,"live_snapshot",return_value=states()),\
             patch.object(M,"guest_txn",return_value={"state":"staged","backups_integrity_verified":True}) as txn,\
             patch.object(M,"reload_entry") as reload:
            with contextlib.redirect_stdout(io.StringIO()):
                M.run()
            txn.assert_called_once_with("verify")
            reload.assert_not_called()

    def test_success_only_reloads_entry(self):
        with patch.object(sys,"argv",["program","--promote"]),\
             patch.object(M.os,"geteuid",return_value=0),\
             patch.object(M,"approval",return_value={}),\
             patch.object(M,"live_snapshot",return_value=states()),\
             patch.object(M,"guest_txn",side_effect=[
               {"state":"staged","backups_integrity_verified":True},
               {"state":"applied_pending_runtime_verification"},
               {"state":"applied_pending_runtime_verification"}]) as txn,\
             patch.object(M,"reload_entry") as reload,\
             patch.object(M,"loaded",return_value=states()):
            with contextlib.redirect_stdout(io.StringIO()):
                M.run()
            self.assertEqual([x.args[0] for x in txn.call_args_list],
                             ["verify","commit","verify"])
            reload.assert_called_once_with()

    def test_failed_reload_rolls_back_and_reloads_original(self):
        with patch.object(sys,"argv",["program","--promote"]),\
             patch.object(M.os,"geteuid",return_value=0),\
             patch.object(M,"approval",return_value={}),\
             patch.object(M,"live_snapshot",return_value=states()),\
             patch.object(M,"guest_txn",side_effect=[
               {"state":"staged","backups_integrity_verified":True},
               {"state":"applied_pending_runtime_verification"},
               {"state":"applied_pending_runtime_verification"},
               {"state":"rolled_back"}]) as txn,\
             patch.object(M,"reload_entry",side_effect=[M.Blocked("initial reload failed"),None]) as reload,\
             patch.object(M,"loaded",return_value=states()):
            with contextlib.redirect_stdout(io.StringIO()),self.assertRaisesRegex(M.Blocked,"initial reload failed"):
                M.run()
            self.assertEqual([x.args[0] for x in txn.call_args_list],
                             ["verify","commit","verify","rollback"])
            self.assertEqual(reload.call_count,2)

if __name__=="__main__":
    unittest.main()
