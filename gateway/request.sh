#!/usr/bin/env bash
set -euo pipefail
echo "=== AUDIO/DNS/CLOCK PRECHANGE AUDIT ==="
date -Is

echo "===== SERVER RANGE AVAILABILITY 220-240 ====="
for ip in $(seq 220 240); do
  addr="10.10.10.$ip"
  if ping -c1 -W1 "$addr" >/dev/null 2>&1; then state=USED; else state=FREE_OR_SILENT; fi
  mac=$(ip neigh show "$addr" | awk '{print $5,$6}')
  printf '%-14s %-14s %s\n' "$addr" "$state" "$mac"
done

for X in "nodea 214" "nodeb 219"; do
  set -- $X; H=$1; ID=$2
  echo; echo "===== $H AUDIO VM $ID ====="
  timeout 20s ssh -o BatchMode=yes "$H" "qm guest exec $ID -- /bin/bash -lc \"hostname; echo --net--; ip -br -4 addr; echo --routes--; ip route; echo --network-config--; cat /etc/network/interfaces 2>/dev/null || true; ls -l /etc/systemd/network /etc/NetworkManager/system-connections 2>/dev/null || true; echo --services--; systemctl list-unit-files | grep -Ei 'bluetooth|pipewire|pulse|audio|speaker|chime|piper' || true; echo --bt--; bluetoothctl devices 2>/dev/null || true; bluetoothctl info 73:81:7B:84:2A:AB 2>/dev/null || true; echo --local-files--; find /opt /usr/local /etc/systemd/system -maxdepth 3 -type f 2>/dev/null | grep -Ei 'audio|speaker|chime|clock|piper|westminster' | head -100 || true\" 2>&1 || true"
done

echo; echo "===== DNS A/B CONFIG ====="
for H in nodea nodeb; do
  echo "--- $H ---"
  timeout 20s ssh -o BatchMode=yes "$H" '
    for id in 217 218; do
      pct status "$id" >/dev/null 2>&1 || continue
      pct exec "$id" -- sh -lc '"'"'hostname; ip -br -4 a; ps aux | grep -Ei "AdGuard|dnsmasq|unbound" | grep -v grep || true; find /opt /etc -maxdepth 3 -type f \( -iname "*adguard*" -o -iname "*dnsmasq*" -o -iname "*rewrite*" \) 2>/dev/null | head -80'"'"'
    done
  ' || true
done

echo; echo "===== HA-GENERAL ACCESS HELPERS ====="
timeout 20s ssh -o BatchMode=yes nodeb 'find /root /opt /usr/local /home -maxdepth 4 -type f 2>/dev/null | grep -Ei "ha.*(token|api|config)|testing.*dashboard|homeassistant" | head -100 || true'
