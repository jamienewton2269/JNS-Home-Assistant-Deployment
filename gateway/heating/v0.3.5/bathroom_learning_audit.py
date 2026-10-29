#!/usr/bin/env python3
"""Read-only Home Assistant bathroom precision/whole-house representativeness audit."""
import base64,json,sys,time
sys.path.insert(0,"gateway/arrival_lighting")
from readiness_probe import ssh_host
INNER=r'''
import datetime,json,math,pathlib,sqlite3,statistics
home=pathlib.Path("/config")
db=home/"home-assistant_v2.db"
ids={
"bathroom_temperature":"sensor.0xa4c1382471d2ed23_temperature",
"bathroom_humidity":"sensor.0xa4c1382471d2ed23_humidity",
"house_thermostat":"sensor.thermostat_thermostat_indoor_temperature",
"outdoor_honeywell":"sensor.thermostat_thermostat_outdoor_temperature",
}
con=sqlite3.connect("file:"+str(db)+"?mode=ro",uri=True,timeout=9)
con.execute("PRAGMA query_only=ON")
now=datetime.datetime.now(datetime.timezone.utc).timestamp()
cutoff=now-72*3600
data={}
for label,eid in ids.items():
 rows=con.execute("""SELECT s.state,s.last_updated_ts FROM states s
 JOIN states_meta m ON s.metadata_id=m.metadata_id
 WHERE m.entity_id=? AND s.last_updated_ts>=?
 ORDER BY s.last_updated_ts ASC""",(eid,cutoff)).fetchall()
 vals=[]
 for value,t in rows:
  try:
   n=float(value)
   if math.isfinite(n):vals.append((t,n))
  except (TypeError,ValueError):pass
 data[label]=vals
def desc(values):
 if not values:return {"points":0}
 nums=[v for _,v in values]
 days=sorted(set(round(v,2) for v in nums))
 return {"points":len(values),"last_recorded_value":nums[-1],
    "latest_state_change_age_minutes":round((now-values[-1][0])/60,1),
    "minimum":min(nums),"maximum":max(nums),
    "median":round(statistics.median(nums),2),
    "first_change_age_hours":round((now-values[0][0])/3600,1),
    "unique_values":len(days)}
result={"hours":72,"temperature":{k:desc(v) for k,v in data.items()}}
# A device's unchanged MQTT updates often don't generate a Recorder state
# change: these ages are not proof of disconnected sensors.
temp=data["bathroom_temperature"];humid=data["bathroom_humidity"]
# A large bathroom temperature range may be showers, physical exposure
# or spikes. Return counts rather than personal occupancy timelines.
step_changes=[(b[1]-a[1],(b[0]-a[0])/60) for a,b in zip(temp,temp[1:])]
result["bathroom_step_counts"]={
  "jumps_ge_1c":sum(abs(d)>=1 for d,m in step_changes),
  "jumps_ge_2c":sum(abs(d)>=2 for d,m in step_changes),
  "jumps_ge_3c":sum(abs(d)>=3 for d,m in step_changes),
  "rapid_jump_ge_1c_within_15min":sum(abs(d)>=1 and m<=15 for d,m in step_changes)
}
# Compare approximate contemporaneous recorded events; this is a low-quality
# proxy since thermostat is whole-degree quantised and changes infrequently.
thermo=data["house_thermostat"]
offsets=[]
for t,bath in temp:
 prior=[x for x in thermo if 0<=t-x[0]<=2*3600]
 if prior:offsets.append(bath-prior[-1][1])
result["bathroom_minus_honeywell"]={
 "comparison_points":len(offsets),
 "median_c":round(statistics.median(offsets),2) if offsets else None,
 "minimum_c":round(min(offsets),2) if offsets else None,
 "maximum_c":round(max(offsets),2) if offsets else None,
 "caution":"thermostat data is sparse; offsets are not time-aligned live estimates"
}
print(json.dumps(result,sort_keys=True))
'''
cmd="exec(__import__('base64').b64decode('"+base64.b64encode(INNER.encode()).decode()+"'))"
r=json.loads(ssh_host("nodeb",["qm","guest","exec","905","--","docker","exec","homeassistant","python3","-c",cmd]))
end=time.monotonic()+100
while not r.get("exited"):
 if not isinstance(r.get("pid"),int) or time.monotonic()>end:raise RuntimeError("sensor comparison timed out")
 time.sleep(1)
 r=json.loads(ssh_host("nodeb",["qm","guest","exec-status","905",str(r["pid"])]))
if r.get("exitcode")!=0:
 print("JNS_BATHROOM_COMPARISON_FAILED",(r.get("err-data") or "")[-250:])
 raise SystemExit(2)
print("JNS_BATHROOM_COMPARISON",r.get("out-data") or "")
