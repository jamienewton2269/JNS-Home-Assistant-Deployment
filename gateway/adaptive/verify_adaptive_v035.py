#!/usr/bin/env python3
"""Verify deployed Adaptive Intelligence with only local protected read access."""
import base64,shlex,subprocess
code=r'''
import json,urllib.request
token=open("/etc/jns/credentials/ha-general.token").read().strip()
def req(path):
    r=urllib.request.Request("http://ha-general.home.arpa/api"+path,
                            headers={"Authorization":"Bearer "+token})
    with urllib.request.urlopen(r,timeout=15) as f:return json.load(f)
states={s["entity_id"]:s for s in req("/states")}
names=("sensor.adaptive_intelligence_observations",
       "sensor.adaptive_intelligence_lighting_state_transitions",
       "sensor.adaptive_intelligence_mqtt_action_capture",
       "sensor.adaptive_intelligence_physical_input_candidates",
       "sensor.adaptive_intelligence_lighting_habit_candidates",
       "sensor.adaptive_intelligence_lighting_habit_early_patterns")
missing=[]
for name in names:
    record=states.get(name)
    if record is None:
        print("MISSING",name)
        missing.append(name)
    else:
        print("VERIFIED",name,repr(record["state"])[:85])
services=[s for s in req("/services") if s["domain"]=="adaptive_intelligence"]
print("ADAPTIVE_SERVICES",sorted(services[0]["services"]) if services else [])
for source in ("sensor.adaptive_intelligence_lighting_habit_early_patterns",
               "sensor.adaptive_intelligence_lighting_habit_candidates"):
    for row in states.get(source,{}).get("attributes",{}).get("patterns",[])[:12]:
        print("HABIT_LIGHT_NAME",row.get("entity"),
              states.get(row.get("entity"),{}).get("attributes",{}).get("friendly_name","unverified"))
        print("HABIT_PATTERN",json.dumps({
            "entity":row.get("entity"),"action":row.get("action"),
            "typical_time":row.get("typical_time"),"day_class":row.get("day_class"),
            "distinct_days":row.get("distinct_days"),"span_days":row.get("span_days"),
            "confidence":row.get("confidence")
        },sort_keys=True))
if missing or not services:raise RuntimeError("Adaptive integration not fully registered")
print("V035_LIVE_VERIFIED")
'''
cmd="python3 -c "+shlex.quote("exec(__import__('base64').b64decode('"+base64.b64encode(code.encode()).decode()+"'))")
p=subprocess.run(["ssh","-T","-o","BatchMode=yes",
                  "-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=7",
                  "root@10.10.110.13",cmd],capture_output=True,text=True,timeout=45)
if p.returncode:raise RuntimeError("HA API status verification failed: "+p.stderr[-330:])
print(p.stdout)
