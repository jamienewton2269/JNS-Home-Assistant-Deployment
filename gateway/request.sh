#!/usr/bin/env bash
set -euo pipefail
ssh nodeb '
  echo "=== HTML AROUND MAIN FORM ==="
  sed -n "635,715p" /opt/natural-automation/natural_automation.py
  echo
  echo "=== expected request-card ids ==="
  grep -nE "id=reqcard|id=\"reqcard\"|id=reqtext|id=\"reqtext\"" /opt/natural-automation/natural_automation.py || true
  echo
  echo "=== post helper ==="
  grep -n "async function post" /opt/natural-automation/natural_automation.py | head -1 | cut -d: -f1 | {
    read n || true; if [ -n "$n" ]; then sed -n "$((n-5)),$((n+20))p" /opt/natural-automation/natural_automation.py; fi
  }
'
