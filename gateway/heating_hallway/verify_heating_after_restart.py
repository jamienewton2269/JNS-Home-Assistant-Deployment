#!/usr/bin/env python3
"""Read only heating acceptance snapshot, using protected credentials on Node C."""
import base64,shlex,subprocess
code=r'''
import json,urllib.request
k=open("/etc/jns/credentials/ha-general.token").read().strip()
req=urllib.request.Request("http://ha-general.home.arpa/api/states",headers={"Authorization":"Bearer "+k})
with urllib.request.urlopen(req,timeout=15) as r: data=json.load(r)
s={d["entity_id"]:d for d in data}
names=[
"automation.jns_heating_predictive_home_10am_and_learned_bedtime_setback",
"automation.jns_heating_explicit_bedtime_activation_ends_earlier_manual_hold",
"input_boolean.jns_heating_automatic_override",
"input_boolean.jns_heating_manual_setpoint_hold",
"input_boolean.general_bedtime_mode",
"alarm_control_panel.house_alarm",
"sensor.jns_heating_verified_alarm_state",
"sensor.jns_heating_predictive_preheat_minutes",
"sensor.jns_hallway_house_temperature",
"sensor.jns_hallway_adaptive_warmup_minutes",
"input_number.jns_hallway_warmup_observations",
"climate.thermostat_thermostat",
"binary_sensor.lyric_home_heating_heating_call",
"binary_sensor.jns_fireplace_override_safe",
]
for entity in names:
 d=s.get(entity)
 if d is None:print(entity,"NOT_FOUND");continue
 attrs=d.get("attributes",{})
 print(entity,d["state"],"target=",attrs.get("temperature"),
       "current=",attrs.get("current_temperature"),
       "hvac_action=",attrs.get("hvac_action"),
       "last_triggered=",attrs.get("last_triggered"))
'''
cmd="python3 -c "+shlex.quote("exec(__import__('base64').b64decode('"+base64.b64encode(code.encode()).decode()+"'))")
r=subprocess.run(["ssh","-T","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes",
                 "root@10.10.110.13",cmd],capture_output=True,text=True,timeout=50)
if r.returncode:raise RuntimeError("Protected read-only HA status query failed: "+r.stderr[:200])
print(r.stdout)
