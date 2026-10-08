#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
BASE=/mnt/data/supervisor/homeassistant
OUT=/opt/jns-ha-control-plane/reports
mkdir -p "$OUT"
LOG="$OUT/ha905-socket-mapping-$(date +%Y%m%dT%H%M%S).log"
RUNNER=(runuser -u github-runner -- ssh -o BatchMode=yes -o ConnectTimeout=8 -o StrictHostKeyChecking=yes -o HostName=10.10.10.235 nodeb)
guest() {
 local cmd="$1" output
 output=$(timeout 28 "${RUNNER[@]}" "timeout 18 qm guest exec 905 -- /bin/sh -c $(printf '%q' "$cmd")") || { echo "GUEST CONNECTION FAILED" >&2; return 1; }
 printf '%s' "$output" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("out-data",""),end=""); print(d.get("err-data",""),end="",file=sys.stderr); sys.exit(d.get("exitcode",125) if d.get("exited") else 124)'
}
{
 echo "=== HA905 PHYSICAL DEVICE MAPPING $(date -Is) ==="
 echo "[1/3] Guest tools"
 guest 'command -v jq || true; command -v grep; command -v base64; command -v sed'
 echo "[2/3] Identify infrastructure socket entity and device registry matches"
 # jq parses directly inside guest, reducing many seconds of agent transfer to one call.
 guest "if command -v jq >/dev/null; then jq -r '.data.entities[] | select((.entity_id + \" \" + (.name // \"\") + \" \" + (.original_name // \"\")) | test(\"nas|wdmycloud|draytek|router\";\"i\")) | [.entity_id,.device_id,.platform,(.name // \"\"),(.original_name // \"\"),(.disabled_by // \"\")] | @tsv' '$BASE/.storage/core.entity_registry'; else echo 'NO_JQ: safe automatic mapping not available'; fi"
 echo "[3/3] Dashboard entity references and integration definitions"
 guest "grep -nE '^(  - title:|    path:| *- domain:| *- label:| *- entity:| *confirmation:| *action: toggle)' '$BASE/dashboards/testing.yaml' | head -100"
 echo "END. NO HA CONFIGURATION CHANGES."
} 2>&1 | tee "$LOG"
echo "Report: $LOG"
