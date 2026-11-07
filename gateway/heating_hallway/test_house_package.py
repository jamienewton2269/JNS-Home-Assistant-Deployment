"""Test candidate HA package, fire interlock and new forecast-only charting."""
from pathlib import Path
import unittest
import yaml
from jinja2 import Environment

ROOT=Path(__file__).resolve().parent
RAW=(ROOT/"jns_hallway_fireplace_package.yaml.template").read_text()
PKG=yaml.safe_load(RAW)

class HousePackageTests(unittest.TestCase):
    def test_template_schema_and_source_tokens(self):
        self.assertIn("__HALLWAY_TEMP_ENTITY__",RAW)
        self.assertIn("__FIREPLACE_TEMP_ENTITY__",RAW)
        self.assertIn("__NATIVE_HALLWAY_FORECAST_ENTITY__",RAW)
        self.assertIn("__NATIVE_HALLWAY_LEARNING_ENTITY__",RAW)
        self.assertEqual(set(PKG["input_boolean"]),{"jns_fireplace_override_enabled"})
        self.assertEqual(len(PKG["template"][0]["sensor"]),5)
        self.assertEqual(len(PKG["template"][1]["binary_sensor"]),2)
    def test_jinja_syntax(self):
        env=Environment()
        for section in PKG["template"]:
            for category in ("sensor","binary_sensor"):
                for item in section.get(category,[]):
                    for name in ("state","availability"):
                        if item.get(name):env.parse(item[name])
                    for v in item.get("attributes",{}).values():
                        if isinstance(v,str) and ("{{" in v or "{%" in v):
                            env.parse(v)
    def test_fire_control_is_fail_closed(self):
        safe=next(s for s in PKG["template"][1]["binary_sensor"]
                  if s["name"]=="JNS Fireplace Override Safe")
        for expression in ("hall >= 19","future >= 18.5","weather_valid",
                           "source_correct","valid",
                           "binary_sensor.jns_fireplace_heat_detected",
                           "input_boolean.jns_heating_automatic_override"):
            self.assertIn(expression,safe["state"])
        fire=next(s for s in PKG["template"][1]["binary_sensor"]
                  if s["name"]=="JNS Fireplace Heat Detected")
        self.assertEqual(fire["delay_on"],"00:15:00")
        self.assertEqual(fire["delay_off"],"00:30:00")
    def test_no_bathroom_as_control_or_direct_boiler_cmd(self):
        self.assertNotIn("bathroom",RAW.lower())
        self.assertNotIn("climate.set_temperature",RAW)
    def test_existing_schedule_fire_override_after_alarm_guards(self):
        schedule=(ROOT.parent/"heating_presence"/"jns_predictive_schedule.yaml").read_text()
        self.assertIn("sensor.jns_hallway_house_temperature",schedule)
        self.assertNotIn("sensor.jns_house_temperature",schedule)
        self.assertNotIn("sensor.lyric_home_heating_thermal_learning",schedule)
        away=schedule.index("{% elif alarm == 'armed_away' %}")
        invalid=schedule.index("{% elif alarm not in ['disarmed', 'armed_home'] %}")
        fireplace=schedule.index("{% elif is_state('binary_sensor.jns_fireplace_override_safe', 'on') %}")
        self.assertLess(away,fireplace)
        self.assertLess(invalid,fireplace)
        self.assertIn("or is_state('binary_sensor.jns_fireplace_heat_detected','on')",schedule)

if __name__=="__main__":unittest.main()
