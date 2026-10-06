#!/usr/bin/env bash
set -euo pipefail

echo "=== NATURAL AUTOMATION + STEWARD INVENTORY ==="
echo "nodec=$(hostname) user=$(whoami)"
date -Is

echo
echo "=== Node C local candidates ==="
find /opt /srv /home -maxdepth 4 \( -iname '*natural*automation*' -o -iname '*steward*' \) -print 2>/dev/null | head -100 || true

echo
echo "=== Permanent SSH path checks ==="
for host in 10.10.10.235 10.10.10.226; do
  echo "--- $host ---"
  ssh -o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=accept-new root@"$host" 'hostname; pveversion 2>/dev/null || true; echo OK' || true
done

echo
echo "=== Node B: locate Natural Automation + HA-General VM ==="
ssh -o BatchMode=yes -o ConnectTimeout=5 root@10.10.10.235 '
  set -u
  hostname
  echo "-- VMs --"
  qm list || true
  echo "-- LXCs --"
  pct list || true
  echo "-- Natural Automation candidates --"
  find /opt /srv /root /var/lib -maxdepth 4 \( -iname "*natural*automation*" -o -iname "*steward*" \) -print 2>/dev/null | head -100 || true
  echo "-- VM905 status/config --"
  qm status 905 2>/dev/null || true
  qm config 905 2>/dev/null | sed -n "1,100p" || true
' || true

echo
echo "=== HA-General network probe from Node C ==="
for ip in 10.10.10.223 10.10.10.224 10.10.10.225 10.10.10.226; do
  printf "%s " "$ip"
  if timeout 2 bash -c "</dev/tcp/$ip/8123" 2>/dev/null; then echo "HA8123=OPEN"; else echo "HA8123=closed"; fi
done

echo
echo "=== DONE ==="
