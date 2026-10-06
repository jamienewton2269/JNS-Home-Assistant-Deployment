#!/usr/bin/env bash
set -euo pipefail
ssh nodeb 'bash -s' <<'REMOTE'
set -u
for i in $(seq 1 12); do
  state=$(systemctl is-active jns-ha-replication.service 2>/dev/null || true)
  echo "CHECK $i $(date -Is) state=$state"
  tail -8 /var/lib/jns-ha-replication/last-run.log 2>/dev/null || true
  echo
  if [ "$state" != "activating" ]; then break; fi
  sleep 20
done
echo "FINAL"
systemctl --no-pager status jns-ha-replication.service | head -35 || true
echo "SUCCESS"
cat /var/lib/jns-ha-replication/last-success 2>/dev/null || true
cat /var/lib/jns-ha-replication/last-success-time 2>/dev/null || true
REMOTE
