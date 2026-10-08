#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
OUT=/opt/jns-ha-control-plane/reports
mkdir -p "$OUT"
STAMP=$(date +%Y%m%dT%H%M%S)
REPORT="$OUT/ha905-dashboard-audit-$STAMP.txt"
ssh_runner(){ /usr/sbin/runuser -u github-runner -- ssh -o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=yes -o HostName=10.10.10.235 nodeb "$@"; }
# Python via guest agent is read-only and reports only relevant entity metadata and dashboard references.
GUEST='python3 -c '"'"'import json,pathlib,re
root=pathlib.Path("/mnt/data/supervisor/homeassistant")
def read(p):
 try: return json.loads(p.read_text())
 except Exception as e: return {"error":str(e)}
reg=read(root/".storage/core.entity_registry").get("data",{}).get("entities",[])
dev=read(root/".storage/core.device_registry").get("data",{}).get("devices",[])
names={d.get("id"):d.get("name_by_user") or d.get("name") for d in dev}
pattern=re.compile("nas|wdmycloud|draytek|router|light|plug|socket|0x",re.I)
print("=== MATCHING ENTITIES (no credentials) ===")
for e in reg:
 eid=e.get("entity_id",""); nm=e.get("name") or e.get("original_name") or ""
 if pattern.search(eid+" "+str(nm)+" "+str(names.get(e.get("device_id")))):
  print(json.dumps({"entity_id":eid,"name":nm,"device_name":names.get(e.get("device_id")),"device_id":e.get("device_id"),"platform":e.get("platform"),"disabled_by":e.get("disabled_by")},ensure_ascii=False))
print("=== TESTING DASHBOARD CURRENT CONTENT ===")
p=root/"dashboards/testing.yaml"
if p.exists():
 for i,line in enumerate(p.read_text().splitlines(),1):
  if re.search("nas|wdmycloud|draytek|router|light|plug|socket|entity:|title:|path:",line,re.I):
   print(f"{i}: {line[:200]}")
else: print("missing")
'"'"''
{
 echo "=== HA905 DASHBOARD / ENTITY MAPPING AUDIT $(date -Is) ==="
 ssh_runner "qm guest exec 905 -- /bin/sh -c $(printf '%q' "$GUEST")"
} | tee "$REPORT"
echo "Report: $REPORT"
