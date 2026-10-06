#!/usr/bin/env bash
set -euo pipefail

echo "=== NODE C ROOT SSH GATEWAY CHECK ==="
echo "runner=$(hostname) user=$(whoami)"
date -Is

echo
echo "sudo:"
if sudo -n true; then echo "sudo_noninteractive=YES"; else echo "sudo_noninteractive=NO"; exit 20; fi

echo
echo "root ssh material:"
sudo -n bash -lc 'ls -la /root/.ssh 2>/dev/null || true; echo; sed -n "1,160p" /root/.ssh/config 2>/dev/null || true'

echo
echo "root -> Node B:"
sudo -n ssh -o BatchMode=yes -o ConnectTimeout=7 -o StrictHostKeyChecking=accept-new root@10.10.10.235 '
  echo HOST=$(hostname)
  pveversion || true
  echo "-- VMs --"
  qm list || true
  echo "-- LXCs --"
  pct list || true
  echo "-- Natural Automation candidates --"
  find /opt /srv /root /var/lib -maxdepth 4 \( -iname "*natural*automation*" -o -iname "*steward*" \) -print 2>/dev/null | head -100 || true
'

echo
echo "root -> Node A:"
sudo -n ssh -o BatchMode=yes -o ConnectTimeout=7 -o StrictHostKeyChecking=accept-new root@10.10.10.226 '
  echo HOST=$(hostname)
  pveversion || true
  qm list || true
' || true

echo
echo "DONE"
