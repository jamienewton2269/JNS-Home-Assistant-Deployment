"""Production schedule regression: Hallway measured cycles may adjust time,
never replace the user's physical Honeywell target."""
import pathlib,unittest,yaml
P=pathlib.Path(__file__).resolve().parents[1]/"heating_presence"/"jns_predictive_schedule.yaml"
D=yaml.safe_load(P.read_text())
A={x['id']:x for x in D['automation']}
T={x['name']:x for x in D['template'][0]['sensor']}
class Regression(unittest.TestCase):
 def test_manual_capture_remains(self):
  self.assertIn('jns_heating_capture_honeywell_manual_target_v1',A)
  self.assertIn('jns_heating_manual_setpoint_hold',D['input_boolean'])
  self.assertIn('JNS_MANUAL_HIGH_HEAT_PRESERVED_V1',P.read_text())
 def test_10am_warmup_uses_hallway_not_quantized_honeywell(self):
  x=T['JNS Heating Predictive Preheat Minutes']
  self.assertIn('sensor.jns_hallway_house_temperature',x['state'])
  self.assertIn('sensor.jns_hallway_adaptive_warmup_minutes',x['state'])
  self.assertNotIn('sensor.lyric_home_heating_thermal_learning',x['state'])
  self.assertIn('120',x['state'])
  self.assertEqual(x['attributes']['target_time'],'10:00')
 def test_cooling_fallback_no_false_learner(self):
  x=T['JNS Heating Predictive Cooling Minutes']
  self.assertNotIn('sensor.lyric_home_heating_thermal_learning',x['state'])
  self.assertIn('60',x['state'])
 def test_manual_priority_before_fireplace(self):
  desired=A['jns_heating_alarm_predictive_target_v1']['actions'][1]['variables']['desired']
  self.assertLess(desired.index("jns_heating_manual_setpoint_hold"),
                  desired.index("jns_fireplace_override_safe"))
  self.assertLess(desired.index("alarm == 'armed_away'"),
                  desired.index("jns_fireplace_override_safe"))
 def test_no_direct_fireplace_control_without_verified_gate(self):
  raw=P.read_text()
  self.assertIn("is_state('binary_sensor.jns_fireplace_override_safe','on')",raw)
  self.assertIn('climate.thermostat_thermostat',raw)
if __name__=='__main__':unittest.main()
