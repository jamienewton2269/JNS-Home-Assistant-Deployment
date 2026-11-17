#!/usr/bin/env python3
"""Read-only heating diagnosis run via Node C -> Node B guest -> HA container.
No Home Assistant API token, state writes, or actuator commands.
"""
import base64,subprocess,json,sys
inside=r'''
import datetime,json,sqlite3,pathlib,yaml
R=pathlib.Path("/config")
print("CHECK_UTC",datetime.datetime.now(datetime.timezone.utc).isoformat())
schedule=R/"packages/jns_heating_predictive_schedule.yaml"
d=yaml.safe_load(schedule.read_text())
print("PACKAGE_AUTOMATIONS")
for a in d.get("automation",[]):
    print("AUTOMATION_DEF",json.dumps({"id":a.get("id"),"alias":a.get("alias"),"triggers":a.get("triggers"),"conditions":a.get("conditions"),"actions":a.get("actions")},default=str,ensure_ascii=True)[:12000])
for section in ("template","input_boolean","input_number"):
    print("PACKAGE_SECTION",section,json.dumps(d.get(section),default=str,ensure_ascii=True)[:12000])
db=sqlite3.connect("file:"+str(R/"home-assistant_v2.db")+"?mode=ro",uri=True,timeout=12)
db.row_factory=sqlite3.Row
names=db.execute("SELECT entity_id FROM states_meta WHERE entity_id LIKE ? OR entity_id LIKE ? OR entity_id LIKE ?",("%heat%","%thermo%","%hallway%")).fetchall()
specific=[
"climate.thermostat_thermostat",
"input_boolean.jns_heating_manual_setpoint_hold",
"input_boolean.jns_heating_suspend_automatic",
"input_boolean.general_bedtime_mode",
"input_datetime.jns_heating_last_bedtime_hold_reset",
"input_datetime.jns_heating_last_manual_selection",
"sensor.jns_heating_schedule_decision",
"sensor.jns_hallway_adaptive_warmup_minutes",
"input_number.jns_hallway_warmup_observations",
"sensor.hallway_thermometer_temperature",
"sensor.jns_heating_active_requested_target",
"binary_sensor.lyric_home_heating_heating_call",
]
known={r["entity_id"] for r in names}
ids=specific+[x for x in known if ("preheat" in x or "schedule" in x or "manual" in x or "warmup" in x) and x not in specific]
for entity in ids:
    rows=db.execute("""SELECT s.state,s.last_updated_ts FROM states s
       JOIN states_meta m ON s.metadata_id=m.metadata_id
       WHERE m.entity_id=? ORDER BY s.state_id DESC LIMIT 6""",(entity,)).fetchall()
    print("RECENT",entity,json.dumps([{"at":datetime.datetime.fromtimestamp(r["last_updated_ts"],datetime.timezone.utc).isoformat() if r["last_updated_ts"] else None,"state":r["state"]} for r in rows],default=str))
print("TODAY_START")
start=datetime.datetime(2026,11,17,6,tzinfo=datetime.timezone.utc).timestamp()
end=datetime.datetime(2026,11,17,11,10,tzinfo=datetime.timezone.utc).timestamp()
for entity in specific:
    rows=db.execute("""SELECT s.state,s.last_updated_ts FROM states s
      JOIN states_meta m ON s.metadata_id=m.metadata_id
      WHERE m.entity_id=? AND s.last_updated_ts BETWEEN ? AND ?
      ORDER BY s.state_id DESC LIMIT 70""",(entity,start,end)).fetchall()
    if rows:
        result=[{"at":datetime.datetime.fromtimestamp(r["last_updated_ts"],datetime.timezone.utc).strftime("%H:%M:%S"),"state":r["state"]} for r in reversed(rows)]
        print("TODAY",entity,json.dumps(result))
print("AUDIT_COMPLETE")
'''
encoded=base64.b64encode(inside.encode()).decode()
import time
sys.path.insert(0,"gateway/arrival_lighting")
from readiness_probe import ssh_host
pycmd="exec(__import__('base64').b64decode('"+encoded+"'))"
out=json.loads(ssh_host("nodeb",["qm","guest","exec","905","--",
                                "docker","exec","homeassistant","python3","-c",pycmd]))
for _ in range(45):
    if out.get("exited"): break
    if not isinstance(out.get("pid"),int): raise RuntimeError("Guest diagnostic process has no PID")
    time.sleep(2)
    out=json.loads(ssh_host("nodeb",["qm","guest","exec-status","905",str(out["pid"])]))
if not out.get("exited"):raise RuntimeError("Guest diagnostic timed out")
if out.get("exitcode")!=0:raise RuntimeError("Guest audit failed: "+out.get("err-data","")[:700])
if out.get("out-truncated"):print("WARNING audit output truncated")
print(out.get("out-data",""))
