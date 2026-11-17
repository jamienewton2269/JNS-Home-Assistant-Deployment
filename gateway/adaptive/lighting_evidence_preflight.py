#!/usr/bin/env python3
"""Sanitised live Adaptive Intelligence and Zigbee evidence audit (read only)."""
import base64, shlex, subprocess
payload=r'''
import json,urllib.request,collections
tok=open("/etc/jns/credentials/ha-general.token").read().strip()
req=urllib.request.Request("http://ha-general.home.arpa/api/states",headers={"Authorization":"Bearer "+tok})
with urllib.request.urlopen(req,timeout=18) as f: states=json.load(f)
for s in states:
 eid=s["entity_id"]
 if (eid.startswith("event.") or (eid.startswith("sensor.") and eid.endswith("_action")) or
     eid in ("sensor.adaptive_intelligence_observations","sensor.adaptive_intelligence_physical_input_candidates",
             "sensor.adaptive_intelligence_lighting_habit_candidates",
             "sensor.jns_lighting_effective_lux",
             "sensor.0xa4c1383917c90309_outdoor_lux_10_minute_average")):
  print("ENTITY",eid,repr(s["state"])[:80],"last_changed",s.get("last_changed"))
'''
cmd="python3 -c "+shlex.quote("exec(__import__('base64').b64decode('"+base64.b64encode(payload.encode()).decode()+"'))")
p=subprocess.run(["ssh","-T","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes",
                  "-o","ConnectTimeout=7","root@10.10.110.13",cmd],capture_output=True,text=True,timeout=50)
if p.returncode:raise RuntimeError("Read-only HA inspection failed: "+p.stderr[:250])
print(p.stdout[-14000:])
