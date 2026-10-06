#!/usr/bin/env bash
set -euo pipefail
echo "=== INSPECT EXISTING JNS HA SYNC / FAILOVER ==="
for host in nodea nodeb; do
  echo
  echo "### $host"
  ssh -o BatchMode=yes -o ConnectTimeout=10 "$host" 'bash -s' <<'REMOTE'
set -u
for f in /root/jns-maintenance/sync_0_5_1.py /root/jns-maintenance/deploy_sync.py /usr/local/sbin/jns-maint-ha-failover /etc/systemd/system/jns-ha-guest-sync.service /etc/systemd/system/jns-ha-guest-sync.timer; do
  echo
  echo "===== $f ====="
  if [ -f "$f" ]; then timeout 8s sed -n '1,260p' "$f"; else echo MISSING; fi
done
echo
echo "===== MAINTENANCE TREE ====="
find /root/jns-maintenance -maxdepth 2 -type f -printf '%TY-%Tm-%Td %TH:%TM %8s %p\n' 2>/dev/null | sort
REMOTE
done
