#!/usr/bin/env python3
"""Strict read-only Zigbee2MQTT/HA-General TS0201 link diagnostic (VM905/CT214)."""
import json,re,sys
sys.path.insert(0,"gateway/arrival_lighting")
from readiness_probe import ssh_host

def read(node,args):
 try:
  return ssh_host(node,args)
 except Exception as exc:
  return "UNAVAILABLE:"+type(exc).__name__

out={}
out["ct214_status"]=read("nodeb",["pct","status","214"]).strip()[:160]
out["ct212_status"]=read("nodeb",["pct","status","212"]).strip()[:160]
# Inspect journal only; omit token/address-like lines and trim noise.
j=read("nodeb",["pct","exec","214","--","journalctl","--since","-3 hours","-n","160","--no-pager","-o","cat"])
sel=[]
for line in j.splitlines():
 if any(key in line.lower() for key in ("a4c13880bb5cffff","summer house sensor","summer_house_sensor")) or any(x in line.lower() for x in
     ("zigbee2mqtt started","zigbee2mqtt stopped","mqtt connected","mqtt disconnected",
      "connection refused","device interview","unavailable","failed to publish")):
  if re.search(r"(?i)(password|token|secret|authorization|permit_join|network_key)",line):continue
  sel.append(re.sub(r"(\b\d{1,3}\.){3}\d{1,3}\b","[ip]",line[:190]))
out["log_signals"]=sel[-30:]
out["service_status"]=read("nodeb",["pct","exec","214","--","systemctl",
    "is-active","zigbee2mqtt"]).strip()[:60]
out["mqtt_service"]=read("nodeb",["pct","exec","212","--","systemctl",
    "is-active","mosquitto"]).strip()[:60]
# Only export this device's possible temperature offset, never the MQTT
# credentials, network keys or complete Zigbee2MQTT configuration.
shell="""for file in /opt/zigbee2mqtt/data/configuration.yaml /var/lib/zigbee2mqtt/data/configuration.yaml /var/lib/zigbee2mqtt/configuration.yaml; do
 if test -f "$file"; then
  grep -i -A 8 -m1 '0xa4c13880bb5cffff' "$file" || true
  break
 fi
done"""
block=read("nodeb",["pct","exec","214","--","sh","-c",shell])
out["temperature_calibration_declared"]=bool(re.search(r"(?m)^\\s*temperature_calibration\\s*:",block))
cal=re.search(r"(?im)^\\s*temperature_calibration\\s*:\\s*(-?\\d+(?:\\.\\d+)?)",block)
out["temperature_calibration"]=float(cal.group(1)) if cal else None
print("JNS_TS0201_LINK_READONLY",json.dumps(out,sort_keys=True))
