"""Passive Hallway native stage: critical safety invariants."""
import pathlib,unittest
import yaml
p=pathlib.Path(__file__).resolve().with_name("jns_hallway_observer.yaml.template")
doc=yaml.safe_load(p.read_text())
class Safety(unittest.TestCase):
    def test_no_thermostat_service_calls(self):
        raw=p.read_text()
        for command in ("climate.set_temperature","climate.set_hvac_mode","homeassistant.restart","input_boolean.turn_off"):
            self.assertNotIn("action: "+command,raw)
    def test_identity_placeholders_remain(self):
        raw=p.read_text()
        self.assertEqual(raw.count("__HALLWAY_TEMP_ENTITY__"),3)
        self.assertEqual(raw.count("__FIREPLACE_TEMP_ENTITY__"),3)
    def test_weather_service_native_open_meteo(self):
        t=[v for v in doc['template'] if 'actions' in v]
        self.assertEqual(len(t),1)
        self.assertEqual(t[0]['actions'][0]['action'],'weather.get_forecasts')
        self.assertEqual(t[0]['actions'][0]['target']['entity_id'],'weather.ha_general')
    def test_fireplace_override_safe_never_activates_in_shadow(self):
        t=[s for v in doc['template'] for s in v.get('binary_sensor',[]) if s['name']=='JNS Fireplace Override Safe']
        self.assertEqual(len(t),1)
        self.assertEqual(t[0]['state'],'false')
    def test_new_sources_are_named(self):
        names=[x['name'] for v in doc['template'] for x in v.get('sensor',[])]
        self.assertIn('JNS Hallway House Temperature',names)
        self.assertIn('JNS Fireplace Temperature',names)
        self.assertIn('JNS Hallway Hourly Open Meteo',names)
if __name__=='__main__':unittest.main()
