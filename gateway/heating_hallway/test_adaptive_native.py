"""Hallway adaptive learner safety and source epoch metadata."""
import unittest,pathlib,yaml
P=pathlib.Path(__file__).with_name("jns_hallway_adaptive_learning.yaml")
D=yaml.safe_load(P.read_text())
class Safety(unittest.TestCase):
 def test_no_climate_commands(self):
  raw=P.read_text()
  self.assertNotIn("action: climate.",raw)
  self.assertNotIn("action: alarm_control_panel.",raw)
 def test_real_heat_call_required(self):
  a=next(a for a in D['automation'] if a['id']=="jns_hallway_observe_warmup_start_v1")
  self.assertIn("binary_sensor.lyric_home_heating_heating_call",str(a))
  self.assertIn("binary_sensor.jns_fireplace_heat_detected",str(a))
 def test_observation_only_and_three_cycle_gate(self):
  x=next(x for t in D['template'] for x in t['sensor']
   if x['name']=='JNS Hallway Adaptive Warmup Minutes')
  self.assertIn("n >= 3",x['state'])
  self.assertIn('hallway-precision-v1',x['attributes']['source_epoch'])
  self.assertIn("120",x['state'])
  self.assertIn("jns_hallway_weather_input_status",x['state'])
 def test_future_only_when_heating(self):
  x=next(x for t in D['template'] for x in t['sensor']
   if x['name']=='JNS Hallway Predicted 60m While Heating')
  self.assertIn('lyric_home_heating_heating_call',x['availability'])
  self.assertEqual(x['attributes']['forecast_scope'],'heating-only')
if __name__=='__main__':unittest.main()
