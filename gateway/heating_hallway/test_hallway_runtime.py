"""AST-only proof source-specific learner is advisory and separate."""
import ast
from pathlib import Path
import unittest
SOURCE=(Path(__file__).parent/"candidate/hallway_runtime.py").read_text()
TREE=ast.parse(SOURCE)

class HallwayRuntimeTests(unittest.TestCase):
    def test_model_is_source_epoch_isolated(self):
        self.assertIn('EPOCH="hallway-precision-v1"',SOURCE)
        self.assertIn('jns_heating_hallway_zone_',SOURCE)
        self.assertNotIn("jns_heating_bathroom_zone_",SOURCE)
        self.assertNotIn("bathroom_reference",SOURCE)
    def test_no_actuators_or_heating_commands(self):
        self.assertNotIn("climate.set_temperature",SOURCE)
        self.assertNotIn("async_call(",SOURCE)
        self.assertNotIn("set_hvac_mode",SOURCE)
        self.assertIn('"control_outputs":False',SOURCE)
    def test_fire_tainted_history_is_excluded(self):
        self.assertIn('status.state!="off"',SOURCE)
        self.assertIn("f-temperature>=1.5",SOURCE)
        self.assertIn("not fire",SOURCE)
    def test_candidate_coordinator_and_sensors_no_bathroom(self):
        module=Path(__file__).parent/"candidate"
        coordinator=(module/"coordinator.py").read_text()
        sensor=(module/"sensor.py").read_text()
        ast.parse(coordinator)
        ast.parse(sensor)
        self.assertNotIn("BathroomAdvisory",coordinator)
        self.assertNotIn("bathroom",sensor.lower())
        self.assertIn("HallwayAdvisory",coordinator)
        self.assertIn('"hallway": hallway',coordinator)
        self.assertIn("class HallwayForecast(",sensor)
        self.assertIn("class HallwayLearning(",sensor)
        self.assertIn("source_epoch",sensor)
        self.assertIn("weather_forecast_fresh",sensor)

    def test_persisted_samples_only_from_same_epoch(self):
        self.assertIn('saved.get("source_epoch")==EPOCH',SOURCE)
        self.assertIn("weather_forecast_fresh",SOURCE)
        self.assertIn("self.last_accepted",SOURCE)

if __name__=="__main__":unittest.main()
