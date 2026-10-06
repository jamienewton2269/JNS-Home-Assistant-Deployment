#!/usr/bin/env bash
set -euo pipefail
echo "=== NATURAL AUTOMATION LIVE INSPECTION ==="
date -Is

ssh nodeb '
  set -e
  echo "HOST=$(hostname)"
  echo "=== /opt/natural-automation ==="
  find /opt/natural-automation -maxdepth 3 -type f -printf "%p %s bytes\n" | sort | head -200
  echo
  echo "=== natural_automation.py head ==="
  sed -n "1,260p" /opt/natural-automation/natural_automation.py 2>/dev/null || true
  echo
  echo "=== service/process ==="
  systemctl list-unit-files | grep -Ei "natural|steward" || true
  systemctl list-units --all | grep -Ei "natural|steward" || true
  ps aux | grep -Ei "[n]atural.?automation|[s]teward" || true
  echo
  echo "=== config/data dirs ==="
  find /opt/natural-automation -maxdepth 2 -type d -print
  echo
  echo "=== VM905 network ==="
  qm status 905
  qm config 905
  echo
  echo "=== guest network agent ==="
  qm guest cmd 905 network-get-interfaces 2>&1 || true
  echo
  echo "=== ARP/DHCP hints ==="
  ip neigh show | grep -i "BC:24:11:35:29:7B" || true
  grep -R -i "BC:24:11:35:29:7B" /var/lib/misc /var/lib/dhcp /etc 2>/dev/null | head -20 || true
'

echo
echo "=== Probe likely HA-General addresses from Node C ==="
for ip in $(seq 101 240); do
  addr="10.10.10.$ip"
  if timeout 0.25 bash -c "</dev/tcp/$addr/8123" 2>/dev/null; then
    echo "$addr:8123 OPEN"
  fi
done
