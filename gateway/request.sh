#!/usr/bin/env bash
set -euo pipefail

echo "=== HA-GENERAL DNS + NATURAL AUTOMATION ACCESS CHECK ==="
date -Is
echo "runner=$(hostname)"
echo

timeout 15s ssh -o BatchMode=yes nodeb 'bash -s' <<'REMOTE'
set -u

echo "=== HA-GENERAL HTTP PORTS ==="
for u in http://10.10.10.223/ http://10.10.10.223:8123/; do
  printf "%s -> " "$u"
  curl -sS -o /dev/null -w "%{http_code}\n" --max-time 3 "$u" || echo "unreachable"
done

echo
echo "=== ADGUARD HOME PROCESS/CONFIG ==="
pct exec 218 -- sh -lc '
  ps wwaux | grep "[A]dGuardHome" || true
  find /opt /etc /var/lib -maxdepth 3 -type f -name "AdGuardHome.yaml" -print 2>/dev/null
' || true

echo
echo "=== NATURAL AUTOMATION TREE ==="
find /opt/natural-automation -maxdepth 3 -type f -printf "%p\n" 2>/dev/null | sort | head -200 || true

echo
echo "=== NATURAL AUTOMATION API STATUS ==="
curl -sS --max-time 3 http://127.0.0.1:8099/api/status || true
echo

echo
echo "=== SAFE SOURCE HINTS ==="
grep -RniE "lovelace|dashboard|entity_registry|device_registry|area_registry|label_registry|services|config/core|api/steward|ha_url|10\.10\.10\.223" /opt/natural-automation 2>/dev/null |   grep -viE "token|password|secret|authorization|bearer" | head -240 || true
REMOTE
