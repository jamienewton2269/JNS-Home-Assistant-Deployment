#!/usr/bin/env python3
"""Inspect VM905 heating settings without writing or printing credentials."""
import base64, json, subprocess, time, shlex
INSPECT=r'''
import pathlib,yaml,sqlite3,datetime,json,hashlib
r=pathlib.Path("/config")
p=r/"packages/jns_heating_predictive_schedule.yaml"
raw=p.read_bytes()
d=yaml.safe_load(raw)
print("SHA256",hashlib.sha256(raw).hexdigest())
for a in d.get("automation",[]):
 if "predictive" in a.get("id","") or "manual_hold_on_bedtime" in a.get("id","") or "manual_target" in a.get("id",""):
  print("AUTOMATION",a.get("id"),"trigger",repr(a.get("triggers")))
  print("ACTIONS",repr(a.get("actions"))[:17000])
print("HELPERS",list(d.get("input_datetime",{}).keys()))
db=sqlite3.connect("file:"+str(r/"home-assistant_v2.db")+"?mode=ro",uri=True,timeout=14)
names=["input_boolean.jns_heating_manual_setpoint_hold","input_boolean.general_bedtime_mode",
"sensor.jns_heating_schedule_decision","sensor.jns_hallway_adaptive_warmup_minutes",
"sensor.jns_heating_predictive_preheat_minutes","sensor.jns_hallway_house_temperature",
"climate.thermostat_thermostat","input_datetime.jns_heating_last_bedtime_hold_reset",
"input_datetime.jns_heating_last_manual_selection","sensor.jns_heating_verified_alarm_state",
"automation.jns_heating_predictive_home_10am_and_learned_bedtime_setback",
"input_boolean.jns_heating_automatic_override","binary_sensor.lyric_home_heating_heating_call"]
for e in names:
 rows=db.execute("""SELECT s.state,s.last_updated_ts FROM states s JOIN states_meta m ON s.metadata_id=m.metadata_id WHERE m.entity_id=? ORDER BY s.state_id DESC LIMIT 4""",(e,)).fetchall()
 print("RECENT",e,json.dumps([{"state":state,"time":datetime.datetime.fromtimestamp(ts,datetime.timezone.utc).isoformat() if ts else None} for state,ts in rows]))
start=datetime.datetime(2026,11,17,6,tzinfo=datetime.timezone.utc).timestamp()
end=datetime.datetime(2026,11,17,11,10,tzinfo=datetime.timezone.utc).timestamp()
for e in names:
 rows=db.execute("""SELECT s.state,s.last_updated_ts FROM states s JOIN states_meta m ON s.metadata_id=m.metadata_id WHERE m.entity_id=? AND s.last_updated_ts BETWEEN ? AND ? ORDER BY s.state_id DESC LIMIT 22""",(e,start,end)).fetchall()
 if rows: print("MORNING",e,json.dumps([{"state":state,"time":datetime.datetime.fromtimestamp(ts,datetime.timezone.utc).strftime("%H:%M:%S")} for state,ts in reversed(rows)]))
print("AUDIT_COMPLETE")
'''
def run_guest(code):
    encoded=base64.b64encode(code.encode()).decode()
    argv=["qm","guest","exec","905","--","docker","exec","homeassistant","python3","-c",
          'exec(__import__("base64").b64decode("'+encoded+'"))']
    prefix=["ssh","-T","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","HostKeyAlias=nodeb.home.arpa",
            "-o","ConnectTimeout=6","root@10.10.110.12"]
    p=subprocess.run(prefix+[shlex.join(argv)],capture_output=True,text=True,timeout=35)
    if p.returncode:raise RuntimeError("Trusted guest connection unavailable: "+p.stderr[:200])
    j=json.loads(p.stdout)
    for i in range(50):
        if j.get("exited"):break
        time.sleep(1.2)
        p=subprocess.run(prefix+[shlex.join(["qm","guest","exec-status","905",str(j["pid"])])],
                         capture_output=True,text=True,timeout=20)
        if p.returncode:raise RuntimeError("Guest exec status unavailable")
        j=json.loads(p.stdout)
    if not j.get("exited"):raise RuntimeError("Guest timed out")
    if j.get("exitcode"):raise RuntimeError("Guest inspect error: "+str(j.get("err-data",""))[:500])
    print(j.get("out-data",""))
run_guest(INSPECT)
