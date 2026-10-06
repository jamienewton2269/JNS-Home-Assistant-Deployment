#!/usr/bin/env bash
set -euo pipefail
echo "=== CONTROLLED PROMOTION PRECHECK VM902 ==="
echo "SOURCE NODE B"
ssh nodeb '
  qm status 902
  qm config 902 | grep -E "^(name|net0|onboot|memory|scsi0|efidisk0):"
  echo NETWORK
  qm guest cmd 902 network-get-interfaces 2>/dev/null || true
  echo HA
  qm guest exec 902 -- /bin/bash -lc "ha core info 2>/dev/null | head -60 || true" 2>/dev/null || true
  echo REPL
  systemctl is-active jns-ha-replication.service || true
  systemctl is-enabled jns-ha-replication.timer || true
  systemctl list-timers jns-ha-replication.timer --no-pager || true
  cat /var/lib/jns-ha-replication/last-success 2>/dev/null || true
  cat /var/lib/jns-ha-replication/last-success-time 2>/dev/null || true
'
echo "TARGET NODE A"
ssh nodea '
  qm status 902
  qm config 902 | grep -E "^(name|net0|onboot|memory|scsi0|efidisk0):"
'
