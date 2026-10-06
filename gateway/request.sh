#!/usr/bin/env bash
set -euo pipefail
echo "=== HA-GENERAL CORE CHECK RESULT ==="
date -Is
ssh nodeb '
  qm guest exec-status 905 10592 || true
  echo
  echo "=== current natural automation status ==="
  curl -sS http://127.0.0.1:8099/api/status
  echo
  curl -sS -X POST -H "Content-Type: application/json" -d "{}" http://127.0.0.1:8099/api/steward/status
  echo
'
