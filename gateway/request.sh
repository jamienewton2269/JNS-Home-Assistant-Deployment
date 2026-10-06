#!/usr/bin/env bash
set -euo pipefail
ssh nodeb '
  echo "SERVICE"; systemctl is-active jns-ha-replication.service || true
  echo "LOG"; tail -200 /var/lib/jns-ha-replication/last-run.log 2>/dev/null || true
  echo "PROCESS"; ps -eo pid,etime,cmd | grep -E "jns-ha-replicate|zfs send|ssh -i /root/.ssh/jns_ha_replication" | grep -v grep || true
  echo "SUCCESS"; cat /var/lib/jns-ha-replication/last-success 2>/dev/null || true; cat /var/lib/jns-ha-replication/last-success-time 2>/dev/null || true
'
