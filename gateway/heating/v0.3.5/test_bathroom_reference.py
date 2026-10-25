"""Offline, no HA dependencies: shower filtering, stale MQTT and separate epoch."""
from datetime import datetime,timedelta,timezone
from pathlib import Path
import importlib.util
import unittest
spec=importlib.util.spec_from_file_location("jns_bathroom_gate",Path(__file__).with_name("bathroom_reference.py"))
M=importlib.util.module_from_spec(spec)
import sys
sys.modules[spec.name]=M
spec.loader.exec_module(M)

class BathroomGateTest(unittest.TestCase):
    def setUp(self):
        self.gate=M.BathroomLearningGate()
        self.t=datetime(2026,10,25,18,0,tzinfo=timezone.utc)
    def at(self,m,**kw):
        t=self.t+timedelta(minutes=m)
        return self.gate.ingest(now=t,observed_at=t,
            temperature=kw.get("temperature",20.9),
            humidity=kw.get("humidity",58.0),
            honeywell_temperature=kw.get("honeywell_temperature",20.0))
    def test_waits_for_real_temporal_baseline(self):
        self.assertIsNone(self.at(0).temperature_c)
        self.assertIsNone(self.at(5).temperature_c)
        final=self.at(10)
        self.assertEqual(final.status,"eligible")
        self.assertAlmostEqual(final.temperature_c,20.9)
        self.assertTrue(final.advisory_only)
    def test_35_degree_spike_quarantined(self):
        self.at(0);self.at(5);self.at(10)
        raised=self.at(15,temperature=35.73,humidity=80)
        self.assertIsNone(raised.temperature_c)
        self.assertEqual(raised.status,"excluded")
        self.assertIsNone(self.at(20).temperature_c)
        self.assertIsNone(self.at(50).temperature_c)
        self.assertIsNone(self.at(55).temperature_c)
        self.assertAlmostEqual(self.at(60).temperature_c,20.9)
    def test_humidity_spike_blocks(self):
        self.at(0);self.at(5)
        spike=self.at(10,humidity=70.0)
        self.assertIn("humidity rise",spike.reason)
        self.assertIsNone(spike.temperature_c)
        self.assertIsNone(self.at(15).temperature_c)
    def test_rapid_shower_heat_blocks(self):
        self.at(0);self.at(5)
        spike=self.at(10,temperature=21.6,humidity=60)
        self.assertIn("rapid temperature",spike.reason)
    def test_room_divergence_blocks(self):
        self.assertIn("differs",self.at(0,temperature=25).reason)
    def test_stale_retained_zigbee_value_blocks(self):
        observed=self.t
        outcome=self.gate.ingest(now=self.t+timedelta(minutes=20),
            observed_at=observed,temperature=20.9,humidity=58,honeywell_temperature=20)
        self.assertIn("stale",outcome.reason)
    def test_duplicate_reports_do_not_fake_learning_samples(self):
        self.at(0)
        duplicate=self.gate.ingest(now=self.t+timedelta(minutes=5),observed_at=self.t,
            temperature=20.9,humidity=58,honeywell_temperature=20)
        self.assertIsNone(duplicate.temperature_c)
        self.assertIn("not newer",duplicate.reason)
    def test_honeywell_remains_reference_not_output(self):
        a=self.at(0,honeywell_temperature=20)
        self.assertEqual(a.epoch,"bathroom-precision-v1")
        self.assertTrue(a.advisory_only)
    def test_rejects_invalid_sensor(self):
        self.assertIsNone(self.at(0,temperature=float("nan")).temperature_c)
        self.assertIsNone(self.at(5,humidity=float("inf")).temperature_c)
if __name__=="__main__":
    unittest.main()
