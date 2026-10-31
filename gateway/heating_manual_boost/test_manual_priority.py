import unittest
from pathlib import Path
import yaml
from jinja2 import Environment

source=Path(__file__).resolve().parents[1]/"heating_presence"/"jns_predictive_schedule.yaml"
pkg=yaml.safe_load(source.read_text())
automation={a["id"]:a for a in pkg["automation"]}
rule=automation["jns_heating_alarm_predictive_target_v1"]
env=Environment()

def decision(alarm="disarmed",manual=False,target=22,away=15,hour=12):
    expr=rule["actions"][1]["variables"]["desired"]
    values={"alarm":alarm,"minutes_now":hour*60,"preheat":120,
            "user_target":target if manual else 21,"manual_target":target,
            "away_min":away,"cooling":60,"bed_samples":1,
            "bedtime_offset":600,"house_offset":0,
            "is_state":lambda name,state: manual if name.endswith("manual_setpoint_hold") else False}
    return env.from_string(expr).render(**values).strip()

class ManualPriority(unittest.TestCase):
    def test_manual_22_home(self):self.assertEqual(decision(manual=True), "none")
    def test_manual_19_home(self):self.assertEqual(decision(manual=True,target=19), "none")
    def test_default_21(self):self.assertEqual(decision(), "21")
    def test_remote_away_warmup_22(self):self.assertEqual(decision(alarm="armed_away",manual=True), "none")
    def test_away_minimum_15(self):self.assertEqual(decision(alarm="armed_away"), "15")
    def test_away_minimum_lower_manual(self):self.assertEqual(decision(alarm="armed_away",manual=True,target=12), "15")
    def test_unknown_alarm_blocks_automation(self):self.assertEqual(decision(alarm="unknown"), "none")
    def test_only_four_unique_automations(self):
        self.assertEqual(len(automation),4)
        self.assertEqual(len(automation),len(pkg["automation"]))
    def test_automatic_command_marked_before_climate(self):
        acts=[x.get("action") for x in rule["actions"]]
        self.assertLess(acts.index("input_datetime.set_datetime"),acts.index("climate.set_temperature"))
    def test_observer_listens_to_wall_and_ui(self):
        watch=automation["jns_heating_capture_honeywell_manual_target_v1"]
        self.assertEqual(watch["triggers"][0]["attribute"],"temperature")
        self.assertEqual(watch["triggers"][0]["entity_id"],"climate.thermostat_thermostat")
    def test_existing_home_target_and_away_preserved(self):
        code=rule["actions"][1]["variables"]["desired"]
        self.assertIn("alarm == 'armed_away'",code)
        self.assertIn("manual_setpoint_hold",code)
    def test_preheat_uses_current_requested_target(self):
        pre=next(s for b in pkg["template"] for s in b.get("sensor",[])
                 if s["name"]=="JNS Heating Predictive Preheat Minutes")
        self.assertIn("sensor.jns_heating_active_requested_target",pre["state"])
    def test_all_template_syntax(self):
        for b in pkg["template"]:
            for sensor in b.get("sensor",[]):
                for value in [sensor.get("state"),*(sensor.get("attributes") or {}).values()]:
                    if isinstance(value,str):env.parse(value)

if __name__=="__main__":unittest.main()
