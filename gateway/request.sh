#!/usr/bin/env bash
set -euo pipefail

echo "=== HA-GENERAL DNS + DASHBOARD PRECHECK ==="
date -Is
echo "runner=$(hostname)"
echo

timeout 8s ssh -o BatchMode=yes nodeb 'bash -s' <<'REMOTE'
set -euo pipefail

echo "=== VM905 STATUS ==="
timeout 5s qm status 905 || true
echo

echo "=== DNS CT218 ==="
timeout 5s pct status 218 || true
timeout 5s pct config 218 | sed -n '1,80p' || true
echo "-- DNS files --"
timeout 6s pct exec 218 -- sh -lc '
  hostname
  ip -br a
  printf "\n/etc/hosts\n"; sed -n "1,120p" /etc/hosts
  printf "\nDNS-related files\n"; find /etc -maxdepth 3 -type f \( -name "dnsmasq.conf" -o -name "*.hosts" -o -name "Corefile" -o -name "named.conf*" -o -name "unbound.conf*" \) -print 2>/dev/null | head -80
  printf "\nlisteners\n"; ss -ltnup | grep -E ":(53)\\b" || true
' || true

echo
echo "=== VM905 HA CONFIG ROOT ==="
timeout 10s qm guest exec 905 --timeout 6 -- /bin/sh -c '
for p in /mnt/data/supervisor/homeassistant /config; do
  if [ -f "$p/configuration.yaml" ]; then
    echo ROOT=$p
    echo "--- configuration.yaml lovelace lines ---"
    grep -n "^lovelace:" "$p/configuration.yaml" || true
    echo "--- .storage dashboards ---"
    ls -1 "$p/.storage" 2>/dev/null | grep -E "lovelace|dash" || true
    exit 0
  fi
done
exit 2
' || true

echo
echo "=== HA GENERAL HTTP/DNS CURRENT ==="
getent hosts ha-general 2>/dev/null || true
curl -I -sS --max-time 4 http://10.10.10.223/ | head -8 || true
REMOTE
