#!/usr/bin/env bash
set -euo pipefail
ssh nodeb '
  echo "=== configuration.yaml references ==="
  qm guest exec 905 -- docker exec homeassistant sh -lc "grep -n \"natural_automation\|automation:\" /config/configuration.yaml || true"
  echo
  echo "=== configuration.yaml head ==="
  qm guest exec 905 -- docker exec homeassistant sh -lc "sed -n \"1,180p\" /config/configuration.yaml"
  echo
  echo "=== natural_automation.yaml ==="
  qm guest exec 905 -- docker exec homeassistant sh -lc "if [ -f /config/natural_automation.yaml ]; then sed -n \"1,160p\" /config/natural_automation.yaml; else echo MISSING; fi"
'
