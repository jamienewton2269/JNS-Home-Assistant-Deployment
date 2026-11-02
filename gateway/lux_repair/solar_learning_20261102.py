#!/usr/bin/env python3
"""HA-General native solar/daylight learning package, no lighting actuation."""
from pathlib import Path
import os,sys,tempfile,datetime,json,hashlib
import yaml
P=Path("/config/packages/jns_solar_daylight_learning.yaml")
cells=[f"{sun}_{sky}" for sun in ("low","mid","high") for sky in ("clear","cloud")]
numbers={}
for c in cells:
  for metric in ("lux","count"):
    numbers[f"jns_solar_learn_{metric}_{c}"]={
      "name":f"Solar learner {metric} {c}","min":0,"max":130000 if metric=="lux" else 1000000,
      "step":1,"mode":"box","unit_of_measurement":"lx" if metric=="lux" else "samples",
      "initial":0} if False else {
      "name":f"Solar learner {metric} {c}","min":0,"max":130000 if metric=="lux" else 1000000,
      "step":1,"mode":"box","unit_of_measurement":"lx" if metric=="lux" else "samples"}
# Crucial: no 'initial' so restored HA helper values persist restart.
features=r"""{% set e=state_attr('sun.sun','elevation')|float(-90) %}
{% if e < 3 %}low{% elif e < 18 %}mid{% else %}high{% endif %}"""
sky=r"""{% set x=states('weather.ha_general') %}
{% if x in ['unknown','unavailable',''] %}{% set x=states('weather.forecast_home') %}{% endif %}
{{ 'clear' if x in ['sunny','clear-night','partlycloudy'] else 'cloud' }}"""
model=r"""{% set k=states('sensor.jns_solar_learning_cell') %}
{% set n=states('input_number.jns_solar_learn_count_'~k)|float(0) %}
{{ states('input_number.jns_solar_learn_lux_'~k)|float(0)|round(0) if n >= 3 else 'unavailable' }}"""
confidence=r"""{% set k=states('sensor.jns_solar_learning_cell') %}
{% set n=states('input_number.jns_solar_learn_count_'~k)|float(0) %}
{{ 'training' if n < 3 else ('low' if n < 15 else ('medium' if n < 50 else 'high')) }}"""
raw=r"""{{ states('sensor.pj2101a_1p_wifi_smart_meter_power')|float(0)|round(0) if is_number(states('sensor.pj2101a_1p_wifi_smart_meter_power')) else 'unavailable' }}"""
d={
 "input_number":numbers,
 "template":[{"sensor":[
 {"name":"JNS Solar Learning Sun Band","unique_id":"jns_solar_learning_sun_band","state":features},
 {"name":"JNS Solar Learning Sky Band","unique_id":"jns_solar_learning_sky_band","state":sky},
 {"name":"JNS Solar Learning Cell","unique_id":"jns_solar_learning_cell","state":"{{ states('sensor.jns_solar_learning_sun_band') ~ '_' ~ states('sensor.jns_solar_learning_sky_band') }}"},
 {"name":"JNS Solar Learning Estimated Lux","unique_id":"jns_solar_learning_estimated_lux","unit_of_measurement":"lx","state":model},
 {"name":"JNS Solar Learning Confidence","unique_id":"jns_solar_learning_confidence","state":confidence},
 {"name":"JNS Solar Learning Grid Signed W","unique_id":"jns_solar_learning_grid_signed_w","unit_of_measurement":"W","state":raw},
 {"name":"JNS Solar Learning Observation","unique_id":"jns_solar_learning_observation",
  "state":"{{ 'training' if is_state('sun.sun','above_horizon') else 'night' }}",
  "attributes":{
   "sun_elevation":"{{ state_attr('sun.sun','elevation') }}",
   "weather":"{{ states('weather.ha_general') if has_value('weather.ha_general') else states('weather.forecast_home') }}",
   "raw_lux":"{{ states('sensor.0xa4c1383917c90309_illuminance') }}",
   "raw_lux_last_reported":"{{ states.sensor['0xa4c1383917c90309_illuminance'].last_reported.isoformat() if states.sensor['0xa4c1383917c90309_illuminance'] is defined else 'unknown' }}",
   "grid_signed_w":"{{ states('sensor.jns_solar_learning_grid_signed_w') }}",
   "grid_sign_verified":"false",
   "inverter_modbus_w":"{{ states('sensor.solar_inverter_ac_power') }}",
   "note":"Grid meter measures net flow; consumption/generation not inferable without inverter and sign validation"}}]}],
 "automation":[{
  "id":"jns_solar_daylight_learning_20261102",
  "alias":"Solar daylight learner - supervised 5 minute observations",
  "description":"Learns lux conditioned by sun and weather, logs signed grid flow; no lights controlled or solar wattage invented. Modbus input is optional.",
  "triggers":[{"trigger":"time_pattern","minutes":"/5"}],
  "conditions":[{"condition":"state","entity_id":"sun.sun","state":"above_horizon"},
    {"condition":"template","value_template":r"""{{ has_value('sensor.0xa4c1383917c90309_illuminance')
 and states('sensor.0xa4c1383917c90309_illuminance')|float(-1) > 0
 and (as_timestamp(now()) - as_timestamp(states.sensor['0xa4c1383917c90309_illuminance'].last_reported,0)) < 300 }}"""}],
  "actions":[
   {"variables":{
    "cell":"{{ states('sensor.jns_solar_learning_cell') }}",
    "value":"{{ states('sensor.0xa4c1383917c90309_illuminance')|float }}",
    "old":"{{ states('input_number.jns_solar_learn_lux_' ~ cell)|float(0) }}",
    "count":"{{ states('input_number.jns_solar_learn_count_' ~ cell)|float(0) }}"}},
   {"condition":"template","value_template":"{{ cell in " + str(cells).replace("'",'"') + " }}"},
   {"action":"input_number.set_value","target":{"entity_id":"{{ 'input_number.jns_solar_learn_lux_' ~ cell }}"},
    "data":{"value":"{{ (value|float if count|float == 0 else (old|float * 0.90 + value|float * 0.10))|round(0) }}"}},
   {"action":"input_number.set_value","target":{"entity_id":"{{ 'input_number.jns_solar_learn_count_' ~ cell }}"},
    "data":{"value":"{{ [count|int + 1,1000000]|min }}"}}
  ],
  "mode":"single"}]
}
def validate(doc):
 assert len(doc["input_number"])==12
 assert len(doc["automation"])==1
 assert "homeassistant.turn_" not in str(doc)
 assert "solar_inverter_ac_power" in str(doc)
old=P.read_bytes() if P.exists() else None
validate(d)
b=yaml.safe_dump(d,allow_unicode=True,sort_keys=False,width=150).encode()
print("SOLAR_LEARN_PLAN "+json.dumps({"path":str(P),"sha256":hashlib.sha256(b).hexdigest(),"exists":old is not None,"helpers":len(numbers),"cells":cells}),flush=True)
if "--apply" in sys.argv:
 if old is not None and b==old:
  print("SOLAR_LEARN_NO_CHANGE")
 else:
  if old is not None:
   bk=Path("/config/.jns-backups")/("solar-learn-"+datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
   bk.mkdir(parents=True,exist_ok=False)
   (bk/P.name).write_bytes(old)
  fd,tmp=tempfile.mkstemp(dir=str(P.parent),prefix=".solar-learn-")
  with os.fdopen(fd,"wb") as f:f.write(b);f.flush();os.fsync(f.fileno())
  os.chmod(tmp,0o644);os.replace(tmp,P)
  print("SOLAR_LEARN_APPLIED")
