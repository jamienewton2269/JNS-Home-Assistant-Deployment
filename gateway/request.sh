#!/usr/bin/env bash
set -euo pipefail
echo "=== NATURAL AUTOMATION UI DEBUG ==="
date -Is
ssh nodeb '
  set -e
  echo "=== service status ==="
  curl -sS http://127.0.0.1:8099/api/status; echo
  echo
  echo "=== relevant HTML/JS ==="
  grep -nE "Development Node|VM902|Write gate remains disabled|function analyseText|async function go|analyse-start|watchJob|renderProgress|adminstatus|refreshInlineAdmin" /opt/natural-automation/natural_automation.py | sed -n "1,240p"
  echo
  echo "=== JS block around analyseText ==="
  grep -n "function analyseText" /opt/natural-automation/natural_automation.py | head -1 | cut -d: -f1 | {
    read n || true
    if [ -n "$n" ]; then start=$((n-20)); end=$((n+90)); sed -n "${start},${end}p" /opt/natural-automation/natural_automation.py; fi
  }
  echo
  echo "=== recent logs ==="
  journalctl -u natural-automation -n 80 --no-pager
  echo
  echo "=== direct analyse-start smoke test ==="
  curl -sS -X POST -H "Content-Type: application/json" -d "{"text":"turn on the garden waterfeature from 9am until bedtime"}" http://127.0.0.1:8099/api/analyse-start; echo
'
