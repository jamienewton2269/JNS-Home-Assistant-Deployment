#!/usr/bin/env bash
# JNS solar read-only Steward placement and protected recording path check.
set -Eeuo pipefail
export LC_ALL=C
echo "JNS_SOLAR_STEWARD_PLACEMENT_READONLY"
echo "RUNNER_HOST=$(hostname -s)"
echo "=== Node C local service state ==="
for name in natural-automation.service jns-steward.service jns-steward-agent.service jns-management-bridge.service jns-dns-reservation-importer.service; do
  active="$(systemctl is-active "$name" 2>/dev/null || :)"
  enabled="$(systemctl is-enabled "$name" 2>/dev/null || :)"
  echo "SERVICE=$name active=$active enabled=$enabled"
done
for p in /opt/natural-automation /var/lib/jns-steward /opt/jns-steward \
         /opt/jns-ha-control-plane /var/lib/jns-solar \
         /opt/natural-automation/data/knowledge; do
  if test -d "$p"; then
    writable="$(test -w "$p" && echo yes || echo no)"
    echo "DIRECTORY=$p present=yes runner_writable=$writable"
  else echo "DIRECTORY=$p present=no"; fi
done
for host in nodea nodeb; do
  echo "=== HOST=$host Steward presence ==="
  if ! ssh -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=5 "$host" 'test "$(id -u)" = 0' >/dev/null 2>&1; then
    echo "HOST=$host accessible=no"; continue
  fi
  ssh -o BatchMode=yes -o StrictHostKeyChecking=yes "$host" 'bash -s' <<'REMOTE'
for name in natural-automation.service jns-steward.service jns-steward-agent.service jns-infrastructure-discovery.service; do
 echo "SERVICE=$name active=$(systemctl is-active "$name" 2>/dev/null || :)"
done
for p in /opt/natural-automation /opt/natural-automation/data/knowledge /var/lib/jns-steward; do
 if test -d "$p"; then echo "DIRECTORY=$p present=yes"; fi
done
REMOTE
done
echo "JNS_SOLAR_STEWARD_PLACEMENT_COMPLETE"
