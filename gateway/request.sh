#!/usr/bin/env bash
set -euo pipefail
ssh nodeb 'bash -s' <<'REMOTE'
set -u
for i in $(seq 1 14); do
  state=$(systemctl is-active jns-ha-replication.service 2>/dev/null || true)
  echo "CHECK $i $(date -Is) state=$state"
  tail -10 /var/lib/jns-ha-replication/last-run.log 2>/dev/null || true
  [ "$state" != "activating" ] && break
  sleep 30
done
echo "SUCCESS_MARKERS"
cat /var/lib/jns-ha-replication/last-success 2>/dev/null || true
cat /var/lib/jns-ha-replication/last-success-time 2>/dev/null || true
REMOTE
echo "NODE_A_FENCING"
ssh nodea 'for id in 902 903 905; do echo "### $id"; qm status "$id" 2>/dev/null || echo ABSENT; qm config "$id" 2>/dev/null | grep -E "^(name|net0|onboot|scsi0|efidisk0|memory|balloon):" || true; done'
