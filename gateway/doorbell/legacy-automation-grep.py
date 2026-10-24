#!/usr/bin/env python3
"""Inspect legacy YAML lines related to doorbell without modifying HA900."""
import subprocess,shlex,json
def guest(script):
    cmd=['ssh','nodea',shlex.join(['qm','guest','exec','900','--','/bin/sh','-c',script])]
    p=subprocess.run(cmd,capture_output=True,text=True,timeout=25)
    if p.returncode: return 'REMOTE ERROR '+p.stderr[-140:]
    try:
        j=json.loads(p.stdout)
        return (j.get('out-data') or '')[:15000]+'\nEXIT='+str(j.get('exitcode'))
    except Exception:return 'GUEST RESPONSE PARSE ERROR'
paths='/mnt/data/supervisor/homeassistant/automations.yaml /mnt/data/supervisor/homeassistant/scripts.yaml /mnt/data/supervisor/homeassistant/packages/*.yaml'
script="grep -HinEi 'door.?bell|kc868|chime|ding.?dong|mqtt.*press|ring.*bell|alarm.?panel' "+paths+" 2>/dev/null | grep -viE 'password|secret|token|authorization|encryption|api.key' | head -100"
print("LEGACY_AUTOMATION_MATCHES",guest(script),flush=True)
script="grep -nEi 'on_press:|on_click:|mqtt:|KC868-A16-X|KC868-A16-Y|binary_sensor:|switch:' /mnt/data/supervisor/homeassistant/esphome/alarmpanel.yaml | head -110"
print("LEGACY_ESPHOME_MAPPING",guest(script),flush=True)

import re
selected=guest("sed -n '1040,1195p' /mnt/data/supervisor/homeassistant/automations.yaml")
print("LEGACY_BELL_AUTOMATION_DETAILS",flush=True)
for line in selected.splitlines():
    s=line.strip()
    if re.search(r"(?i)^(alias:|id:|description:|trigger:|triggers:|platform:|entity_id:|from:|to:|for:|action:|actions:|service:|delay:|seconds:|minutes:|milliseconds:|counter:|domain:|type:|topic:|event_type:|mode:)",s):
        print(s[:170],flush=True)
