#!/usr/bin/env bash
set -euo pipefail
echo "=== VERIFY NODE C -> A/B AND INVENTORY ==="
echo "runner=$(hostname) user=$(whoami)"
date -Is

for h in nodea nodeb; do
  echo
  echo "=== $h ==="
  ssh -o BatchMode=yes -o ConnectTimeout=7 "$h" '
    set -e
    echo HOST=$(hostname)
    echo USER=$(whoami)
    pveversion | head -1 || true
    echo "-- VMs --"
    qm list || true
    echo "-- LXCs --"
    pct list || true
    echo "-- Natural Automation / Steward candidates --"
    find /opt /srv /root /var/lib -maxdepth 4 \( -iname "*natural*automation*" -o -iname "*steward*" \) -print 2>/dev/null | head -120 || true
  '
done

echo
echo "=== Node B HA-General probes ==="
ssh nodeb '
  set -u
  for vm in 902 903 904 905 906 907 908 909; do
    if qm status "$vm" >/dev/null 2>&1; then
      echo "--- VM$vm ---"
      qm status "$vm" || true
      qm config "$vm" | grep -E "^(name:|net0:|ipconfig0:|description:)" || true
    fi
  done
'

echo
echo "=== DONE ==="
