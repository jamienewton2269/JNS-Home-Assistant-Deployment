#!/usr/bin/env python3
import base64,json,shlex,subprocess,time
SRC=r'''
from pathlib import Path
import json,re,yaml,sqlite3,datetime
P=Path("/config")
autos=yaml.safe_load((P/"automations.yaml").read_text())
ctl=next(a for a in autos if str(a.get("id"))=="1791918795028")
dump=yaml.safe_dump(ctl,sort_keys=False,allow_unicode=True,width=180)
# Relevant fallback lines only.
lines=[s for s in dump.splitlines() if re.search(r"weather|sun|synthetic|stale|effective_lux|decision_lux|raining|fallback",s,re.I)]
print("JNS_LUX_FALLBACK_LINES="+json.dumps(lines[:220]),flush=True)

ids=["weather.forecast_home","weather.ha_general","binary_sensor.outdoor_raining",
     "sensor.jns_lighting_effective_lux","sensor.0xa4c1383917c90309_illuminance",
     "sensor.0xa4c1383917c90309_outdoor_lux_10_minute_average","sun.sun"]
db=P/"home-assistant_v2.db"
out={}
if db.exists():
 c=sqlite3.connect("file:"+str(db)+"?mode=ro",uri=True,timeout=3);cur=c.cursor()
 for eid in ids:
  try:
   cur.execute("""SELECT s.state,s.last_updated_ts FROM states s
     JOIN states_meta m ON s.metadata_id=m.metadata_id
     WHERE m.entity_id=? ORDER BY s.state_id DESC LIMIT 3""",(eid,))
   out[eid]=[{"state":st,"age_s":datetime.datetime.now(datetime.timezone.utc).timestamp()-ts if ts else None,
              "time":datetime.datetime.fromtimestamp(ts,datetime.timezone.utc).isoformat() if ts else None}
             for st,ts in cur.fetchall()]
  except Exception: out[eid]=[]
 c.close()
print("JNS_LUX_FALLBACK_STATES="+json.dumps(out,sort_keys=True),flush=True)
'''
enc=base64.b64encode(SRC.encode()).decode()
code="exec(__import__('base64').b64decode("+repr(enc)+"))"
def ssh(argv):
 p=subprocess.run(["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","nodeb",shlex.join(argv)],
                  capture_output=True,text=True,timeout=35)
 if p.returncode: raise RuntimeError(p.stderr[-500:])
 return json.loads(p.stdout)
d=ssh(["qm","guest","exec","905","--","docker","exec","homeassistant","python3","-c",code]);pid=d.get("pid")
for _ in range(60):
 if d.get("exited"):break
 time.sleep(.5); d=ssh(["qm","guest","exec-status","905",str(pid)])
print(d.get("out-data") or "")
if d.get("exitcode")!=0: raise SystemExit(d.get("exitcode") or 2)
