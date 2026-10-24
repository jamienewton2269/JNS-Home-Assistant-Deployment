#!/usr/bin/env python3
"""Display non-secret doorbell configuration directives for inspection."""
import subprocess,shlex,json
files="/mnt/data/supervisor/homeassistant/esphome/alarmpanel.yaml /mnt/data/supervisor/homeassistant/esphome/esphome-web-630464.yaml"
pattern="doorbell|door.?bell|kc868|chime|buzzer|relay|on_press|on_click|on_boot|mqtt.publish|switch.turn|binary_sensor:|output:|pin:|GPIO|[[:space:]]id:"
shell="grep -nEi "+shlex.quote(pattern)+" "+files+" | grep -viE 'password|secret|encryption|token|api_key|wifi|ssid|authorization' | head -160"
p=subprocess.run(["ssh","nodea","qm guest exec 900 -- /bin/sh -c "+shlex.quote(shell)],capture_output=True,text=True,timeout=25)
print("ESPHOME_SCAN_SSH_EXIT",p.returncode)
try:
    d=json.loads(p.stdout)
    print("ESPHOME_SCAN_GUEST_EXIT",d.get("exitcode"))
    print("ESPHOME_SCAN_LINES",(d.get("out-data") or "")[:19000])
except Exception:
    print("ESPHOME_SCAN_ERROR",p.stderr[-250:])
