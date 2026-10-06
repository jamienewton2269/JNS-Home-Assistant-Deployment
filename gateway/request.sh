#!/usr/bin/env bash
set -euo pipefail
echo "=== CHECK HA-GENERAL NATURAL AUTOMATION INCLUDE ==="
ssh nodeb '
  qm guest exec 905 -- docker exec homeassistant python3 -c "from pathlib import Path; p=Path('/config/configuration.yaml'); print(p.read_text() if p.exists() else 'MISSING')" 2>/dev/null | sed -n "1,220p"
  echo
  echo "=== natural_automation.yaml ==="
  qm guest exec 905 -- docker exec homeassistant python3 -c "from pathlib import Path; p=Path('/config/natural_automation.yaml'); print(p.read_text() if p.exists() else 'MISSING')" 2>/dev/null | sed -n "1,120p"
'
