#!/usr/bin/env bash
set -Eeuo pipefail
echo '=== DNS + HA-GENERAL MAGIC HOME PRECHECK ==='
echo '--- Node C reverse/forward resolver view ---'
getent hosts 10.10.10.170 || true
command -v host >/dev/null && host 10.10.10.170 || true
command -v dig >/dev/null && dig +short -x 10.10.10.170 || true

ssh -o BatchMode=yes -o ConnectTimeout=10 nodeb 'bash -s' <<'NODEB'
set -Eeuo pipefail
echo '--- Node B resolver view ---'
getent hosts 10.10.10.170 || true
command -v host >/dev/null && host 10.10.10.170 || true
command -v dig >/dev/null && dig +short -x 10.10.10.170 || true
echo '--- Explicit internal DNS reverse queries ---'
for dns in 10.10.10.247 10.10.10.248; do
  echo "DNS=$dns"
  if command -v dig >/dev/null; then dig +short -x 10.10.10.170 @"$dns" || true; fi
  if command -v nslookup >/dev/null; then nslookup 10.10.10.170 "$dns" 2>/dev/null || true; fi
done

VMID=905
echo '--- HA-General status ---'
qm status "$VMID"
echo '--- Existing matching config entries/entities ---'
for file in core.config_entries core.device_registry core.entity_registry; do
  qm guest exec "$VMID" -- /bin/bash -lc "grep -iE 'flux_led|b4:e8:42:28:83:28|10.10.10.170|288328|sofa_led' /mnt/data/supervisor/homeassistant/.storage/$file || true" || true
done
NODEB
