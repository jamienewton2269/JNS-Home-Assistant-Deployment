#!/usr/bin/env bash
set -euo pipefail

echo "=== DEPLOY HA-GENERAL DNS + TESTING DASHBOARD ==="
date -Is
echo "runner=$(hostname)"
echo

bash ha_testing_dashboard/deploy-ha-general-testing.sh
