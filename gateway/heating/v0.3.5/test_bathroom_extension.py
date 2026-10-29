"""Static integration safety tests against VM905's audited source baseline."""
import ast
from pathlib import Path
import unittest

ROOT=Path(__file__).with_name("bathroom_extension")
def parse(file):return ast.parse((ROOT/file).read_text())
def classname(tree,name):
    return next(x for x in tree.body if isinstance(x,ast.ClassDef) and x.name==name)
def methods(tree,name):
    return {m.name:m for m in classname(tree,name).body
             if isinstance(m,(ast.FunctionDef,ast.AsyncFunctionDef))}

class ExtensionSafetyTests(unittest.TestCase):
    def test_compiles_candidate_and_isolated_module(self):
        for path in (ROOT/"coordinator.py",ROOT/"sensor.py",
                     ROOT.parent/"bathroom_runtime.py",ROOT.parent/"bathroom_reference.py",
                     ROOT.parent/"thermal.py"):
            compile(path.read_text(),str(path),"exec")
    def test_original_heater_control_methods_identical(self):
        old=methods(parse("baseline/coordinator.py"),"ZoneCoordinator")
        new=methods(parse("coordinator.py"),"ZoneCoordinator")
        for key in ("_demand","_watch_response","_increase_rate","_command_on",
                    "_number","_outdoor","_refresh_forecast","async_start_manual_test",
                    "clear_fault"):
            self.assertEqual(ast.dump(old[key],include_attributes=False),
                             ast.dump(new[key],include_attributes=False),
                             "Protected method changed: "+key)
    def test_existing_heating_sensors_unchanged(self):
        before=parse("baseline/sensor.py")
        after=parse("sensor.py")
        for name in ("ReasonSensor","ResponseSensor","ConfidenceSensor",
                     "IndoorSensor","ProjectedSensor"):
            self.assertEqual(ast.dump(classname(before,name),include_attributes=False),
                             ast.dump(classname(after,name),include_attributes=False),
                             name)
    def test_new_bathroom_advisory_outputs_are_separate(self):
        src=(ROOT/"sensor.py").read_text()
        self.assertIn("class BathroomSourceSensor",src)
        self.assertIn("class BathroomForecastSensor",src)
        self.assertIn("class BathroomQualitySensor",src)
        self.assertIn('self.coordinator.data.get("bathroom")',src)
        # Do not write new model results into the legacy house projected field.
        coordinator=(ROOT/"coordinator.py").read_text()
        self.assertIn('"projected": projected',coordinator)
        self.assertIn('"bathroom": bathroom',coordinator)
        self.assertIn("Optional bathroom learner failed; legacy heating remains authoritative",coordinator)
        self.assertIn("Optional bathroom advisory learner failed to load; existing heating continues",coordinator)
        self.assertNotIn('"projected": bathroom',coordinator)
    def test_distinct_sample_store_epoch(self):
        src=(ROOT.parent/"bathroom_runtime.py").read_text()
        self.assertIn('f"jns_heating_bathroom_zone_{entry.entry_id}"',src)
        self.assertIn('saved.get("source_epoch") == EPOCH',src)
        self.assertNotIn("async_call(",src)
        self.assertNotIn("set_temperature",src)
        self.assertNotIn("set_hvac_mode",src)
        self.assertNotIn("jns_heating_zone_{entry.entry_id}",src)
if __name__=="__main__":unittest.main()
