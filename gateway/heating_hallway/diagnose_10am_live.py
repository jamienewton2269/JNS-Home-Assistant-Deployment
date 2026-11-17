#!/usr/bin/env python3
"""Read-only HA-General 10am heating diagnosis; no control, no secret output."""
import json, urllib.request, urllib.parse, subprocess, shlex, datetime, sys
BASE="http://ha-general.home.arpa/api"
token_path="/etc/jns/credentials/ha-general.token"
with open(token_path) as f: key=f.read().strip()
headers={"Authorization":"Bearer "+key}
def get(path):
    req=urllib.request.Request(BASE+path,headers=headers)
    with urllib.request.urlopen(req,timeout=24) as r:return json.load(r)
print("AUDIT_AT_UTC",datetime.datetime.now(datetime.timezone.utc).isoformat(),flush=True)
states=get("/states")
wanted=("heat","thermo","lyric","hallway","bedtime","warmup","preheat","schedule","comfort","fireplace","outdoor","presence","away")
for item in states:
    e=item["entity_id"]
    if e.startswith(("climate.","automation.","input_boolean.","input_number.","input_datetime.","sensor.","binary_sensor.","timer.")) and any(t in e for t in wanted):
        a=item.get("attributes",{})
        print("STATE",json.dumps({"id":e,"value":item["state"],"changed":item.get("last_changed"),
          "updated":item.get("last_updated"),"temperature":a.get("temperature"),
          "current_temperature":a.get("current_temperature"),"hvac_action":a.get("hvac_action"),
          "last_triggered":a.get("last_triggered"),"friendly_name":a.get("friendly_name")},ensure_ascii=True))
def guest_cat(path):
    command="qm guest exec 905 -- /bin/cat "+shlex.quote(path)
    p=subprocess.run(["ssh","-T","-o","BatchMode=yes","root@nodeb.home.arpa",command],
                    text=True,capture_output=True,timeout=40)
    if p.returncode:raise RuntimeError("Guest read transport failed")
    j=json.loads(p.stdout)
    if j.get("exitcode")!=0 or j.get("out-truncated"):raise RuntimeError("Guest read failed/truncated")
    return j["out-data"].encode("latin1").decode("utf8")
import yaml
p="/mnt/data/supervisor/homeassistant/packages/jns_heating_predictive_schedule.yaml"
d=yaml.safe_load(guest_cat(p))
for item in d.get("automation",[]):
    name=item.get("alias","")
    print("AUTOMATION_DEF",json.dumps({"alias":name,"id":item.get("id"),
      "triggers":item.get("triggers"),"conditions":item.get("conditions"),
      "actions":item.get("actions")},default=str,ensure_ascii=True)[:13000])
for key in ("template","input_boolean","input_number"):
    print("PACKAGE_SECTION",key,json.dumps(d.get(key),default=str,ensure_ascii=True)[:13500])
# HA recorder history is queried selectively for only decision-bearing sensors, not bulk state dump.
entities=[
"climate.thermostat_thermostat",
"input_boolean.jns_heating_manual_setpoint_hold",
"input_boolean.general_bedtime_mode",
"sensor.jns_heating_schedule_decision",
"sensor.jns_hallway_adaptive_warmup_minutes",
"input_number.jns_hallway_warmup_observations",
"sensor.hallway_thermometer_temperature",
"sensor.jns_heating_active_requested_target",
]
start="2026-11-17T06:00:00+00:00"
end="2026-11-17T11:05:00+00:00"
for eid in entities:
    query=urllib.parse.urlencode({"filter_entity_id":eid,"end_time":end,"minimal_response":"true"})
    try:
        history=get("/history/period/"+urllib.parse.quote(start,safe=":")+"?"+query)
        arr=history[0] if history else []
        rows=[{"time":x.get("last_changed") or x.get("last_updated"),"state":x.get("state")} for x in arr]
        print("HISTORY",eid,json.dumps(rows[-35:]))
    except Exception as ex:
        print("HISTORY_UNAVAILABLE",eid,type(ex).__name__)
print("AUDIT_COMPLETE")
