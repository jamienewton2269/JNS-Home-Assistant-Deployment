import unittest
from datetime import datetime, timedelta, timezone
from fireplace_signal import Reading, classify

class FireplaceSignalTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,10,31,14,0,tzinfo=timezone.utc)
        self.house=Reading(20,self.now)
    def test_lit_fire_gradient_and_rise(self):
        result=classify(Reading(24,self.now),self.house,Reading(22,self.now-timedelta(minutes=10)),self.now)
        self.assertEqual(result.state,"likely_on")
        self.assertTrue(result.exclude_from_thermal_learning)
    def test_cold_fireplace(self):
        self.assertEqual(classify(Reading(20.2,self.now),self.house,now=self.now).state,"likely_off")
    def test_stale_is_unknown(self):
        self.assertEqual(classify(Reading(26,self.now-timedelta(minutes=30)),self.house,now=self.now).state,"insufficient_data")
    def test_single_hot_point_is_not_proof(self):
        self.assertEqual(classify(Reading(26,self.now),self.house,now=self.now).state,"insufficient_data")
if __name__=="__main__": unittest.main()
