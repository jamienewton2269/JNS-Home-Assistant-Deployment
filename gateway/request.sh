#!/usr/bin/env bash
set -euo pipefail
ssh nodeb '
  echo "=== NATURAL AUTOMATION MIDDLE SECTION ==="
  sed -n "240,640p" /opt/natural-automation/natural_automation.py
'
