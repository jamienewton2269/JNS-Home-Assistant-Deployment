#!/usr/bin/env bash
# Veyra complete-release acceptance gate. Read-only checks; no display restart.
set -uo pipefail
fail=0
check(){ if "$@" >/dev/null 2>&1; then echo "PASS $*"; else echo "FAIL $*"; fail=$((fail+1)); fi; }
echo "=== Veyra v0.9.3 release acceptance ==="
check systemctl is-active --quiet veyra-kiosk.service
check curl -fsS --max-time 4 http://127.0.0.1:8766/health
check curl -fsS --max-time 4 http://127.0.0.1:8764/health
check grep -Rq '^WorkingDirectory=/opt/veyra' /etc/systemd/system/veyra-kiosk.service.d
check grep -Rq '^Environment=PYTHONPATH=/opt/veyra' /etc/systemd/system/veyra-kiosk.service.d
check grep -q '_start_home_server' /opt/veyra/veyra/kiosk.py
check grep -q 'veyra-programme-discovery-v1' /opt/veyra/veyra/view.py
check test -f /opt/veyra/veyra/local_vault.py
check test -f /opt/veyra/veyra/provider_availability.py
check test -f /opt/veyra/veyra/viewing_history.py
check test -f /opt/veyra/scripts/veyra-input-controller.sh
echo "=== Note ==="
echo "Static checks cannot prove provider-specific Escape, streaming availability, login safety, or clean PXE install."
echo "Run manual physical-device acceptance tests separately."
echo "Failed static checks: $fail"
test "$fail" -eq 0
