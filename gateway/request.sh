#!/usr/bin/env bash
set -euo pipefail
echo "=== NEW HA REPLICA PRE-FLIGHT ==="
ssh -o BatchMode=yes nodeb 'bash -s' <<'REMOTE'
set -euo pipefail
echo "--- NODE B -> NODE A SSH ---"
timeout 8s ssh -o BatchMode=yes -o ConnectTimeout=5 nodea 'hostname; zfs list -H -o name | head -5'
echo
echo "--- SOURCE VM CONFIGS ---"
for id in 902 903 905; do
  echo "### VM$id"
  qm status "$id"
  qm config "$id"
done
echo
echo "--- SOURCE ZFS SNAPSHOTS ---"
for id in 902 903 905; do
  zfs list -H -t snapshot -o name -r vmdata 2>/dev/null | grep -E "^vmdata/vm-$id-disk-" | tail -20 || true
done
echo
echo "--- TARGET STATE ---"
ssh nodea 'for id in 902 903 905; do echo "### VM$id"; qm status "$id" 2>/dev/null || echo ABSENT; qm config "$id" 2>/dev/null || true; done; echo ZFS; zfs list -H -o name,used,refer -r vmdata | grep -E "vm-(902|903|905)-disk-" || true'
REMOTE
