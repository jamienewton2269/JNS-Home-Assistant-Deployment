"""Offline-only safety checks for the JNS 10:00 adaptive warm-up candidate.

No Home Assistant API, guest access, credentials, thermostat commands, or restarts.
"""
import pathlib
import unittest
import yaml
from jinja2 import Environment

ROOT = pathlib.Path(__file__).resolve().parent
PATH = ROOT / "jns_predictive_schedule.yaml"


class AdaptiveWarmupConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = PATH.read_text(encoding="utf-8")
        cls.pkg = yaml.safe_load(cls.raw)
        cls.automations = {a["id"]: a for a in cls.pkg["automation"]}
        cls.sensors = {s["name"]: s for b in cls.pkg["template"] for s in b.get("sensor", [])}

    def test_single_existing_thermostat_owner_retained(self):
        ids = [a["id"] for a in self.pkg["automation"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertIn("jns_heating_alarm_predictive_target_v1", ids)
        self.assertIn("jns_heating_learn_bedtime_v1", ids)
        self.assertIn("jns_heating_observe_morning_warmup_v1", ids)
        observer = self.automations["jns_heating_observe_morning_warmup_v1"]
        self.assertNotIn("climate.set_temperature", str(observer))
        self.assertNotIn("climate.set_hvac_mode", str(observer))
        self.assertNotIn("script.turn_on", str(observer))

    def test_ten_am_deadline_and_overnight_setting(self):
        preheat = self.sensors["JNS Heating Predictive Preheat Minutes"]
        self.assertEqual(preheat["attributes"]["target_time"], "10:00")
        self.assertIn("120", preheat["state"])
        self.assertIn("sensor.lyric_home_heating_thermal_learning", preheat["state"])
        decision = str(self.automations["jns_heating_alarm_predictive_target_v1"])
        self.assertIn("600", decision)  # 10:00
        self.assertIn("21", decision)
        self.assertIn("18", decision)
        self.assertIn("input_boolean.jns_heating_automatic_override", decision)
        self.assertIn("alarm not in ['disarmed', 'armed_home']", decision)
        self.assertIn("climate.thermostat_thermostat", decision)

    def test_observed_source_requires_three_completed_cycles(self):
        preheat = self.sensors["JNS Heating Predictive Preheat Minutes"]
        self.assertIn("jns_heating_warmup_observations", preheat["state"])
        self.assertIn(">= 3", preheat["state"])
        self.assertIn("[360", preheat["state"])
        observation = str(self.automations["jns_heating_observe_morning_warmup_v1"])
        self.assertIn("binary_sensor.lyric_home_heating_heating_call", observation)
        self.assertIn("input_boolean.jns_heating_warmup_heat_seen", observation)
        self.assertIn("input_boolean.jns_heating_warmup_tracking", observation)
        self.assertIn("elapsed_min", observation)
        self.assertIn("minutes_per_degree", observation)

    def test_templates_parse(self):
        env = Environment()
        for item in self.sensors.values():
            if isinstance(item.get("state"), str):
                env.parse(item["state"])
            for v in item.get("attributes", {}).values():
                if isinstance(v, str) and ("{{" in v or "{%" in v):
                    env.parse(v)
        # Runtime Home Assistant rendering and real device behaviour require
        # separate, guarded end-to-end acceptance after the security merger.

    def test_no_disable_of_security_or_other_nodes(self):
        self.assertNotIn("ha-security.home.arpa", self.raw)
        self.assertNotIn("vm906", self.raw.lower())
        self.assertNotIn("qm stop", self.raw)
        self.assertNotIn("ha core restart", self.raw)


if __name__ == "__main__":
    unittest.main()
