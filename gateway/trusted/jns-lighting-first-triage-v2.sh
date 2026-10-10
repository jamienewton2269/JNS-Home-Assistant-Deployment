#!/usr/bin/env bash
# JNS lighting connectivity check, migration plan 2026-10-10.
# Read-only. Planned addresses may differ from running network state.
set -u
echo "JNS LIGHTING TRIAGE v2 $(date -Is)"
echo "Node: $(hostname)"
echo "=== Current routes and DNS ==="
ip -4 route || :
cat /etc/resolv.conf || :
echo
check() {
  local name="$1" ip="$2" port="$3"
  echo "=== $name $ip:$port ==="
  if timeout 4 bash -c 'exec 3<>/dev/tcp/"$1"/"$2"' bash "$ip" "$port" 2>/dev/null; then echo "TCP OPEN"; else echo "TCP CLOSED"; fi
  if [[ "$port" == 8123 || "$port" == 8080 ]]; then
    curl -sS --connect-timeout 3 --max-time 6 -o /dev/null -w 'HTTP %{http_code} %{errormsg}\n' "http://$ip:$port/" || :
  fi
}
check HA900 10.10.110.226 8123
check HA902 10.10.110.220 8123
check HA905 10.10.110.223 8123
check MQTT 10.10.110.230 1883
check Zigbee2MQTT 10.10.110.231 8080
for ip in 10.10.110.247 10.10.110.248; do
 echo "=== DNS $ip ==="
 if command -v dig >/dev/null; then timeout 5 dig +time=2 +tries=1 @"$ip" github.com A +short || :;
 elif command -v nslookup >/dev/null; then timeout 5 nslookup github.com "$ip" || :; fi
done
echo "=== MQTT bridge state (no authentication changes) ==="
if command -v mosquitto_sub >/dev/null; then
 timeout 7 mosquitto_sub -h 10.10.110.230 -p 1883 -t 'zigbee2mqtt/bridge/state' -C 1 -W 5 -v 2>&1 || :
else echo "mosquitto_sub not installed"; fi
echo "READ-ONLY COMPLETE: actual service locations must be verified from these results."
