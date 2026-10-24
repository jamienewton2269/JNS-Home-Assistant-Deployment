#!/usr/bin/env bash
# JNS Steward -> HA-General access audit. Read-only. No secrets or auth files displayed.
set -Eeuo pipefail
exec ssh -o BatchMode=yes -o ConnectTimeout=7 -o StrictHostKeyChecking=yes root@nodeb.home.arpa 'bash -s' <<'NODEB'
set -Eeuo pipefail
echo 'JNS_STEWARD_AUDIT_BEGIN'
if pct status 221 >/dev/null 2>&1; then
  echo "STEWARD_CT221_STATUS=$(pct status 221 | awk '{print $2}')"
  pct exec 221 -- sh -c '
    printf "STEWARD_SERVICE="
    systemctl is-active natural-automation.service 2>/dev/null || true
    printf "STEWARD_SERVICE_USER="
    systemctl show natural-automation.service -p User --value 2>/dev/null || true
    printf "STEWARD_APPLY_DISABLED="
    if grep -qx "NA_ENABLE_APPLY=0" /etc/natural-automation/environment 2>/dev/null; then echo yes; else echo unconfirmed; fi
    printf "STEWARD_BRIDGE_CONFIGURED="
    if grep -q "^NA_PVE_BRIDGE_HOST=" /etc/natural-automation/environment 2>/dev/null; then echo yes; else echo no; fi
    printf "STEWARD_HA_GENERAL_DNS="
    if getent ahosts ha-general.home.arpa >/dev/null 2>&1; then echo resolves; else echo unavailable; fi
    printf "STEWARD_HA_API_HTTP="
    curl -sS --max-time 8 -o /dev/null -w "%{http_code}\n" http://ha-general.home.arpa:8123/api/ || true
    printf "STEWARD_STATUS_API="
    curl -sS --max-time 8 -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8099/api/status || true
  '
else
  echo 'STEWARD_CT221_STATUS=absent_or_unavailable'
fi
printf "HA_GENERAL_VM905="
qm status 905 2>&1 | sed -n "1p"
echo 'JNS_STEWARD_AUDIT_END'
NODEB
