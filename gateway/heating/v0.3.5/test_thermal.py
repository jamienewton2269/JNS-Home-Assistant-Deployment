"""Isolated deterministic tests. Never connect to a live Home Assistant instance."""
import importlib.util
import math
from datetime import datetime,timedelta,timezone
from pathlib import Path
import sys
import unittest

SOURCE=Path(__file__).with_name("thermal.py")
SPEC=importlib.util.spec_from_file_location("jns_thermal_v035_test",SOURCE)
MODULE=importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name]=MODULE
SPEC.loader.exec_module(MODULE)
ZoneLearner=MODULE.ZoneLearner


def series(days=5,quantum=1.0,flat=False,jitter=False):
    """Synthetic physically plausible heating/cooling; no real home measurements."""
    learner=ZoneLearner()
    start=datetime(2026,1,2,tzinfo=timezone.utc)
    now=start
    temperature=19.7
    seconds=0
    for step in range(days*24*12+1):
        hours=seconds/3600
        outdoor=8+4*math.sin(2*math.pi*hours/24)
        heat=1.0 if int(hours//3)%2==0 else 0.0
        display=20.0 if flat else round(temperature/quantum)*quantum
        learner.add(now,display,outdoor,heat)
        dt=(299 if step%2==0 else 301) if jitter else 300
        temperature+=(dt/3600)*(.09*(outdoor-temperature)+1.8*heat+.03)
        now+=timedelta(seconds=dt)
        seconds+=dt
    return learner,now


class LearnerCompatibilityTest(unittest.TestCase):
    def test_existing_storage_schema_untouched(self):
        l,now=series(days=1)
        payload=l.dump()
        self.assertEqual(set(payload[0]),{"at","indoor","outdoor","duty","valid"})
        restored=ZoneLearner(payload)
        self.assertEqual(restored.dump(),payload)
        self.assertIsNone(restored.project(now,[],1.0))
        self.assertEqual(len(restored.samples),len(payload))

    def test_flat_quantised_sensor_cannot_become_ready(self):
        l,_=series(days=5,flat=True,jitter=True)
        status=l.status()
        self.assertFalse(status["ready"],status)
        self.assertEqual(status["nonzero_delta_windows"],0)
        self.assertGreater(status["short_5min_adjacent_pairs"],100)
        self.assertEqual(status["stored_samples"],len(l.samples))

    def test_one_day_is_not_enough_independent_windows(self):
        l,_=series(days=1,quantum=1)
        s=l.status()
        self.assertLess(s["valid_windows"],48)
        self.assertFalse(s["ready"])

    def test_long_multi_day_coarse_data_can_learn(self):
        l,now=series(days=5,quantum=1.0,jitter=True)
        s=l.status()
        self.assertGreaterEqual(s["valid_windows"],48,s)
        self.assertGreater(s["nonzero_delta_windows"],6,s)
        self.assertGreaterEqual(s["indoor_levels"],3,s)
        self.assertGreaterEqual(s["heated_windows"],10,s)
        self.assertGreaterEqual(s["unheated_windows"],10,s)
        self.assertTrue(s["ready"],s)
        forecast=[(now+timedelta(hours=h),8.) for h in range(4)]
        self.assertIsInstance(l.project(now,forecast,1.0),float)
        self.assertIsNone(l.project(now,[],1.0))

    def test_dont_build_windows_across_large_missing_period(self):
        l,now=series(days=2,quantum=.1)
        l.samples[50].at=(datetime.fromisoformat(l.samples[49].at)+
                           timedelta(hours=3)).isoformat()
        status=l.status()
        self.assertGreater(status["clock_or_gap_rejections"],0,status)

    def test_reject_bad_heating_samples(self):
        l=ZoneLearner()
        t=datetime(2026,1,1,tzinfo=timezone.utc)
        l.add(t,20,8,0)
        l.add(t,20,8,0) # duplicate
        l.add(t+timedelta(minutes=5),float("nan"),8,0)
        l.add(t+timedelta(minutes=5),20,8,1.5)
        self.assertEqual(len(l.samples),1)
        l.add(t+timedelta(minutes=5),20,8,1)
        self.assertEqual(len(l.samples),2)

    def test_storage_cap_is_preserved(self):
        l,_=series(days=9,quantum=.1)
        self.assertEqual(len(l.samples),2016)

    def test_invalid_forecast_is_safe(self):
        l,now=series(days=5,quantum=1.0)
        self.assertIsNone(l.project(now,None,1))
        self.assertIsNone(l.project(now,[],1))
        self.assertIsNone(l.project(now,[(now,8.)],-1))
        self.assertIsNone(l.project(now+timedelta(hours=2),[(now,8.)],1.))

if __name__=="__main__":
    unittest.main()
