#!/usr/bin/env bash
set -Eeuo pipefail
echo "=== HA-GENERAL ZIGBEE/UI/AUTOMATION AUDIT ==="
date -Is

ssh nodeb 'bash -s' <<'NODEB'
set -Eeuo pipefail

run() {
  echo
  echo "### $1"
  shift
  timeout 30s qm guest exec 905 -- /bin/bash -lc "$*" 2>&1 || true
}

run "HA core info" 'ha core info'
run "HA config check" 'ha core check'
run "configuration.yaml relevant lines" "grep -nE '^(homeassistant:|automation:|script:|scene:|lovelace:|.*packages:)' /mnt/data/supervisor/homeassistant/configuration.yaml || true"
run "HA config directory" 'ls -la /mnt/data/supervisor/homeassistant | sed -n "1,160p"'
run "Packages" 'find /mnt/data/supervisor/homeassistant/packages -maxdepth 2 -type f -print 2>/dev/null | sort || true'
run "Entity registry counts" 'python3 - <<'"'"'PY'"'"'
import json, pathlib, collections
p=pathlib.Path("/mnt/data/supervisor/homeassistant/.storage/core.entity_registry")
d=json.loads(p.read_text())
ents=d.get("data",{}).get("entities",[])
print("total",len(ents))
domains=collections.Counter(e.get("entity_id","").split(".",1)[0] for e in ents)
print("domains",dict(domains))
for e in ents:
    eid=e.get("entity_id","")
    if eid.startswith(("light.","switch.","sensor.","binary_sensor.","automation.")):
        print("|".join([
            eid,
            str(e.get("platform","")),
            str(e.get("disabled_by","")),
            str(e.get("hidden_by","")),
            str(e.get("name") or e.get("original_name") or "")
        ]))
PY'
run "Automation storage" 'test -f /mnt/data/supervisor/homeassistant/automations.yaml && sed -n "1,260p" /mnt/data/supervisor/homeassistant/automations.yaml || echo "NO automations.yaml"'
run "Lovelace storage files" 'for f in /mnt/data/supervisor/homeassistant/.storage/lovelace*; do [ -e "$f" ] || continue; echo "--- $f"; sed -n "1,260p" "$f"; done'
run "Recent Zigbee/MQTT related core log" 'ha core logs --no-color 2>/dev/null | grep -Ei "zigbee|mqtt|automation|lovelace" | tail -n 180 || true'
NODEB

echo "HA_GENERAL_ZIGBEE_UI_AUDIT_COMPLETE $(date -Is)"
