#!/usr/bin/env python3
import base64,json,shlex,subprocess,time
SRC=r'''
from pathlib import Path
import sqlite3,datetime,json
P=Path("/config"); db=P/"home-assistant_v2.db"
ids=["light.livingroom_pendant","light.0x5c0272fffe400903","light.rgbcw_lightbulb","light.rgbw_lightbulb"]
out={}
c=sqlite3.connect("file:"+str(db)+"?mode=ro",uri=True,timeout=4);cur=c.cursor()
for eid in ids:
 cur.execute("""SELECT s.state,s.last_updated_ts FROM states s JOIN states_meta m ON s.metadata_id=m.metadata_id
 WHERE m.entity_id=? ORDER BY s.state_id DESC LIMIT 20""",(eid,))
 out[eid]=[{"state":st,"time":datetime.datetime.fromtimestamp(ts,datetime.timezone.utc).isoformat() if ts else None}
           for st,ts in cur.fetchall()]
c.close()
print("JNS_CANDIDATE_LIGHT_HISTORY="+json.dumps(out,sort_keys=True),flush=True)
'''
enc=base64.b64encode(SRC.encode()).decode()
code="exec(__import__('base64').b64decode("+repr(enc)+"))"
def ssh(argv):
 p=subprocess.run(["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","nodeb",shlex.join(argv)],capture_output=True,text=True,timeout=40)
 if p.returncode:raise RuntimeError(p.stderr[-500:])
 return json.loads(p.stdout)
d=ssh(["qm","guest","exec","905","--","docker","exec","homeassistant","python3","-c",code]);pid=d.get("pid")
for _ in range(80):
 if d.get("exited"):break
 time.sleep(.5);d=ssh(["qm","guest","exec-status","905",str(pid)])
print(d.get("out-data") or "")
if d.get("exitcode")!=0:raise SystemExit(d.get("exitcode") or 2)
