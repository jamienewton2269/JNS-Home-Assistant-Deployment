#!/usr/bin/env bash
set -Eeuo pipefail

echo "=== NODE C SSH RESOLUTION ==="
for host in ha-general 10.10.110.223; do
  echo "--- $host ---"
  ssh -G "$host" 2>/dev/null | grep -E '^(hostname|user|port|identityfile) ' | head -12 || true
done

echo
echo "=== DIRECT HA SSH PROBE ==="
set +e
for target in ha-general 10.10.110.223; do
  echo "--- $target ---"
  timeout 8 ssh -o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=accept-new "$target" 'echo DIRECT_HA_SSH_OK; hostname' 2>&1
  echo "rc=$?"
done
set -e

echo
echo "=== NODE B / VM905 QGA STATUS ==="
ssh -o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=yes -o HostName=10.10.110.12 nodeb "qm status 905; qm agent 905 ping" || true
