#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
ROOT=/opt/jns-ha-control-plane/reports
mkdir -p "$ROOT"
OUT="$ROOT/ha905-mapping-$(date +%Y%m%dT%H%M%S).txt"
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
ssh_runner() { /usr/sbin/runuser -u github-runner -- ssh -o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=yes -o HostName=10.10.10.235 nodeb "$@"; }
guest() {
  local command="$1" reply
  reply=$(ssh_runner "qm guest exec 905 -- /bin/sh -c $(printf '%q' "$command")")
  printf '%s' "$reply" | python3 -c 'import json,sys; x=json.load(sys.stdin); print(x.get("out-data",""),end=""); print(x.get("err-data",""),file=sys.stderr,end=""); sys.exit(int(x.get("exitcode",1)) if x.get("exited") else 2)'
}
fetch_file() {
 local path="$1" dst="$2" i chunk
 : > "$dst"
 for i in $(seq 0 129); do
  # 3072 bytes encoded safely within guest-agent output limits.
  chunk=$(guest "dd if='$path' bs=3072 skip=$i count=1 2>/dev/null | base64")
  [[ -n "$chunk" ]] || break
  printf '%s' "$chunk" | base64 -d >> "$dst"
 done
}
echo "Reading HA905 metadata through existing github-runner -> Node B -> VM905 guest agent..."
BASE=/mnt/data/supervisor/homeassistant
fetch_file "$BASE/.storage/core.entity_registry" "$TMP/entities.json"
fetch_file "$BASE/.storage/core.device_registry" "$TMP/devices.json"
fetch_file "$BASE/dashboards/testing.yaml" "$TMP/testing.yaml"
python3 - "$TMP" <<'PY' | tee "$OUT"
import json,sys,pathlib,re
p=pathlib.Path(sys.argv[1])
entities=json.loads((p/'entities.json').read_text())['data']['entities']
devices=json.loads((p/'devices.json').read_text())['data']['devices']
lookup={d.get('id'):d.get('name_by_user') or d.get('name') for d in devices}
pat=re.compile('nas|wdmycloud|draytek|router|light|plug|socket|0x',re.I)
print('=== ENTITY REGISTRY MATCHES ===')
for e in entities:
 eid=e.get('entity_id',''); nm=e.get('name') or e.get('original_name') or ''
 d=lookup.get(e.get('device_id'))
 if pat.search(' '.join(map(str,[eid,nm,d]))):
  print(json.dumps(dict(entity_id=eid,name=nm,device_name=d,device_id=e.get('device_id'),platform=e.get('platform'),disabled_by=e.get('disabled_by')),ensure_ascii=False))
print('=== DASHBOARD REFERENCED ENTITIES / RELEVANT LINES ===')
for i,line in enumerate((p/'testing.yaml').read_text().splitlines(),1):
 if re.search('nas|wdmycloud|draytek|router|light|plug|socket|entity:|title:|path:',line,re.I):
  print(f'{i}: {line[:240]}')
print('=== END: read-only ===')
PY
echo "Report: $OUT"

