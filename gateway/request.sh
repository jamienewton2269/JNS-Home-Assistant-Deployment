#!/usr/bin/env bash
set -euo pipefail

echo "=== FIX AND VALIDATE HA-GENERAL TESTING DASHBOARD YAML ==="
date -Is
echo "runner=$(hostname)"
echo

DASH="ha_testing_dashboard/testing-dashboard.yaml"
HELPER="ha_testing_dashboard/apply_testing_yaml.py"

[[ -f "$DASH" ]] || { echo "Missing $DASH" >&2; exit 1; }
[[ -f "$HELPER" ]] || { echo "Missing $HELPER" >&2; exit 1; }

echo "Staging corrected dashboard payload on Node B..."
base64 -w0 "$DASH" | timeout 10s ssh -o BatchMode=yes nodeb 'cat >/tmp/jns-testing-dashboard.b64'

echo "Applying and validating inside Home Assistant..."
cat "$HELPER" | timeout 30s ssh -o BatchMode=yes nodeb 'python3 -'

echo
echo "=== HTTP VERIFY ==="
timeout 10s ssh -o BatchMode=yes nodeb "curl -sS -o /dev/null -w 'testing=%{http_code}\n' --max-time 4 http://10.10.10.223/testing-dashboard/commissioning"
