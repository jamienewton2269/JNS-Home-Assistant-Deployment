#!/usr/bin/env bash
set -euo pipefail
ssh nodeb 'bash -s' <<'REMOTE'
set -u
for i in $(seq 1 16); do
  state=$(systemctl is-active jns-ha-replication.service 2>/dev/null || true)
  echo "CHECK $i $(date -Is) state=$state"
  tail -12 /var/lib/jns-ha-replication/last-run.log 2>/dev/null || true
  echo
  [ "$state" != "activating" ] && break
  sleep 30
done
echo "=== FINAL ==="
systemctl is-active jns-ha-replication.service || true
cat /var/lib/jns-ha-replication/last-success 2>/dev/null || true
cat /var/lib/jns-ha-replication/last-success-time 2>/dev/null || true
REMOTE
