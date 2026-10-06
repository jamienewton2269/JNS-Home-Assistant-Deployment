#!/usr/bin/env bash
set -euo pipefail
echo "=== REPLICATION PROGRESS ==="
ssh nodeb '
  systemctl --no-pager status jns-ha-replication.service | head -40 || true
  echo
  echo "--- LAST RUN LOG ---"
  tail -120 /var/lib/jns-ha-replication/last-run.log 2>/dev/null || true
  echo
  echo "--- SUCCESS MARKERS ---"
  cat /var/lib/jns-ha-replication/last-success 2>/dev/null || true
  cat /var/lib/jns-ha-replication/last-success-time 2>/dev/null || true
'
echo
echo "=== NODE A TARGETS ==="
ssh nodea '
  for id in 902 903 905; do
    echo "### VM$id"
    qm status "$id" 2>/dev/null || echo ABSENT
    qm config "$id" 2>/dev/null | grep -E "^(name|memory|balloon|cores|net0|scsi0|efidisk0|onboot|startup|tags):" || true
  done
  echo
  echo "--- REPL SNAPSHOTS ---"
  zfs list -H -t snapshot -o name,creation -s creation 2>/dev/null | grep "jns-repl-" | tail -30 || true
'
