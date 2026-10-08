#!/usr/bin/env bash
set -u
echo "JNS LIGHTING READ-ONLY TRIAGE $(date -Is)"
for entry in "HA902 10.10.10.220 8123" "HA905 10.10.10.223 8123" "MQTT 10.10.10.230 1883" "Zigbee2MQTT 10.10.10.231 8080"; do
 read -r name ip port <<< "$entry"
 echo "=== $name $ip:$port ==="
 timeout 4 bash -c 'exec 3<>/dev/tcp/"$1"/"$2"' bash "$ip" "$port" 2>/dev/null && echo "TCP OPEN" || echo "TCP CLOSED"
 if [[ $port == 8123 || $port == 8080 ]]; then curl -sS --connect-timeout 3 --max-time 6 -o /dev/null -w 'HTTP %{http_code} %{errormsg}\n' "http://$ip:$port/" || :; fi
done
echo "=== MQTT discovery evidence from Node C (only if mosquitto_sub available) ==="
if command -v mosquitto_sub >/dev/null; then
 timeout 8 mosquitto_sub -h 10.10.10.230 -p 1883 -t 'zigbee2mqtt/bridge/state' -C 1 -W 5 -v 2>&1 || :
 timeout 8 mosquitto_sub -h 10.10.10.230 -p 1883 -t 'zigbee2mqtt/bridge/devices' -C 1 -W 5 -v 2>&1 | head -c 12000 || :
 echo
else echo "mosquitto_sub unavailable; no packages installed"; fi
echo "Read-only. No service restarted and no configuration changed."
