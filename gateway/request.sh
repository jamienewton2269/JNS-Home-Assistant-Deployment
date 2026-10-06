#!/usr/bin/env bash
set -euo pipefail
echo "=== NATURAL AUTOMATION WRITE-PATH INSPECTION ==="
date -Is
ssh nodeb '
  set -e
  echo "=== service unit ==="
  systemctl cat natural-automation.service || true
  echo
  echo "=== write/apply references ==="
  grep -nE "ENABLE_APPLY|apply|natural_automation.yaml|ha core check|check_config|reload|rollback|backup" /opt/natural-automation/natural_automation.py | sed -n "1,220p"
  echo
  echo "=== tail ==="
  tail -220 /opt/natural-automation/natural_automation.py
'
