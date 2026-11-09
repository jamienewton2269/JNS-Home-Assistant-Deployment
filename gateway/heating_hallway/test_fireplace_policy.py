"""Offline no-HA-commands regression tests for fireplace safeguard."""
from dataclasses import replace
import unittest
from fireplace_policy import Inputs, decide

BASE = Inputs(
    hallway_c=20.1, fireplace_c=25.0,
    hallway_age_seconds=70, fireplace_age_seconds=90,
    fireplace_sustained=True, projected_hallway_60m_c=19.8,
    prediction_validated=True, prediction_source_epoch="hallway-precision-v1",
    weather_forecast_fresh=True, scheduled_target_c=21,
    alarm_state="disarmed", manual_override=False, override_enabled=True)

class FireplaceTests(unittest.TestCase):
    def test_fire_setback_only_when_safe(self):
        self.assertEqual(decide(BASE).target_c, 18)
        self.assertTrue(decide(BASE).suppress_heating)
    def test_low_now_prevents_suppression(self):
        self.assertEqual(decide(replace(BASE,hallway_c=18.7)).target_c,21)
    def test_predicted_cold_prevents_suppression(self):
        self.assertEqual(decide(replace(BASE,projected_hallway_60m_c=18.4)).target_c,21)
    def test_missing_future_preserves_schedule(self):
        self.assertEqual(decide(replace(BASE,projected_hallway_60m_c=None)).target_c,21)
    def test_wrong_model_epoch_preserves_schedule(self):
        self.assertEqual(decide(replace(BASE,prediction_source_epoch="bathroom-precision-v1")).target_c,21)
    def test_stale_fireplace_preserves_schedule(self):
        self.assertEqual(decide(replace(BASE,fireplace_age_seconds=1801)).target_c,21)
    def test_stale_hallway_preserves_schedule(self):
        self.assertEqual(decide(replace(BASE,hallway_age_seconds=1801)).target_c,21)
    def test_weather_unavailable_preserves_schedule(self):
        self.assertEqual(decide(replace(BASE,weather_forecast_fresh=False)).target_c,21)
    def test_alarm_away_unchanged(self):
        self.assertEqual(decide(replace(BASE,alarm_state="armed_away",scheduled_target_c=15)).target_c,15)
    def test_manual_override_not_affected(self):
        self.assertEqual(decide(replace(BASE,manual_override=True)).target_c,21)
    def test_no_fire_retains_10am(self):
        self.assertEqual(decide(replace(BASE,fireplace_sustained=False)).target_c,21)
    def test_nighttime_18_unmodified(self):
        self.assertEqual(decide(replace(BASE,scheduled_target_c=18)).target_c,18)
    def test_no_sunshine_false_positive(self):
        self.assertEqual(decide(replace(BASE,fireplace_c=21.9)).target_c,21)
    def test_sensor_outlier_blocked(self):
        self.assertEqual(decide(replace(BASE,fireplace_c=99)).target_c,21)

if __name__=="__main__": unittest.main()
