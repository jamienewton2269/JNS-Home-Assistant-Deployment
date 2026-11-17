#!/usr/bin/env python3
"""Read-only authenticated Home Assistant status/history; never log credentials."""
import datetime,json,urllib.request,urllib.parse
base="http://ha-general.home.arpa/api"
token=open("/etc/jns/credentials/ha-general.token").read().strip()
def get(path):
    req=urllib.request.Request(base+path,headers={"Authorization":"Bearer "+token})
    with urllib.request.urlopen(req,timeout=14) as f:return json.load(f)
print("AUDIT_UTC",datetime.datetime.now(datetime.timezone.utc).isoformat(),flush=True)
arr=get("/states")
terms=("heat","thermo","lyric","hallway","bedtime","warmup","preheat","schedule","comfort","fireplace")
for a in arr:
    eid=a["entity_id"]
    if eid.startswith(("climate.","automation.","input_boolean.","input_number.","input_datetime.","sensor.","binary_sensor.")) and any(x in eid for x in terms):
        d=a.get("attributes",{})
        obj={"entity":eid,"state":a["state"],"last_changed":a.get("last_changed"),
             "last_triggered":d.get("last_triggered"),"target":d.get("temperature"),
             "current":d.get("current_temperature"),"hvac_action":d.get("hvac_action")}
        print("LIVE",json.dumps(obj,sort_keys=True))
selected=(
"climate.thermostat_thermostat",
"input_boolean.jns_heating_manual_setpoint_hold",
"input_boolean.general_bedtime_mode",
"sensor.jns_heating_schedule_decision",
"sensor.jns_hallway_adaptive_warmup_minutes",
"input_number.jns_hallway_warmup_observations",
"sensor.jns_hallway_house_temperature",
"sensor.jns_heating_active_requested_target",
"binary_sensor.lyric_home_heating_heating_call",
)
for date in ("2026-11-16","2026-11-17"):
    start=date+"T06:00:00+00:00";end=date+"T11:15:00+00:00"
    for eid in selected:
        q=urllib.parse.urlencode({"filter_entity_id":eid,"end_time":end,"minimal_response":"true"})
        try:
            d=get("/history/period/"+urllib.parse.quote(start,safe=":")+"?"+q)
            values=d[0] if d else []
            rows=[{"at":x.get("last_changed") or x.get("last_updated"),
                   "state":x.get("state")} for x in values]
            print("MORNING",date,eid,json.dumps(rows[-24:]))
        except Exception as e:
            print("HISTORY_UNAVAILABLE",date,eid,type(e).__name__)
print("AUDIT_COMPLETE")
