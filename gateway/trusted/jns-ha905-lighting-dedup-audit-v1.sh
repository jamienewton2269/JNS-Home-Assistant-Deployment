#!/usr/bin/env bash
# JNS lighting/dashboard dedup audit — read-only. Run on Node C.
set -Eeuo pipefail
umask 077
OUT="/opt/jns-ha-control-plane/reports"
mkdir -p "$OUT"
STAMP="$(date +%Y%m%dT%H%M%S)"
REPORT="$OUT/lighting-entity-audit-$STAMP.txt"
exec > >(tee "$REPORT") 2>&1
echo "JNS lighting entity audit $(date -Is)"
echo "Host: $(hostname)"
echo "This script only performs REST GET requests; no switching or configuration changes."
echo "It requires a HA905 long-lived access token, entered without echo and kept only in memory."
read -rsp 'HA905 long-lived access token (not stored): ' TOKEN
echo
if [[ -z "$TOKEN" ]]; then echo "No token supplied, exiting without changes"; exit 2; fi
BASE='http://10.10.10.223:8123'
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"; unset TOKEN' EXIT
for endpoint in states config; do
  code=$(curl --silent --show-error --connect-timeout 4 --max-time 25 \
    -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
    -o "$TMP/$endpoint.json" -w '%{http_code}' "$BASE/api/$endpoint") || { echo "HA905 connection failed"; exit 3; }
  if [[ "$code" != 200 ]]; then echo "HA905 API $endpoint HTTP $code. Stop; check token/connection."; exit 4; fi
done
python3 - "$TMP/states.json" <<'PY'
import json,sys
data=json.load(open(sys.argv[1]))
words=('nas','server','wdmycloud','draytek','router','zigbee','light','socket','plug')
print('\n=== POSSIBLE DUPLICATES AND LIGHT CONTROLS ===')
print('ENTITY_ID | STATE | FRIENDLY_NAME | RESTORED | DEVICE_CLASS')
for x in sorted(data,key=lambda x:x['entity_id']):
 e=x['entity_id']; a=x.get('attributes',{})
 n=str(a.get('friendly_name',''))
 if e.startswith(('light.','switch.')) or any(w in (e+' '+n).lower() for w in words):
  print(' | '.join([e,str(x.get('state','')),n,str(a.get('restored','')),str(a.get('device_class',''))]))
print('\nEntities:',len(data))
PY
echo
echo "Report: $REPORT"
echo "Token not saved. Review mappings before hiding ANY dashboard card."
echo "IMPORTANT: report may contain local entity names. Share only if comfortable."
