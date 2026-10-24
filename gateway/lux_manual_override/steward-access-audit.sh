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
echo "HOST_STEWARD_SERVICE=$(systemctl is-active natural-automation.service 2>/dev/null || true)"
echo "HOST_STEWARD_ENABLED=$(systemctl is-enabled natural-automation.service 2>/dev/null || true)"
echo "HOST_STEWARD_SERVICE_USER=$(systemctl show natural-automation.service -p User --value 2>/dev/null || true)"
if test -f /opt/natural-automation/natural_automation.py; then echo 'HOST_STEWARD_SOURCE=present';else echo 'HOST_STEWARD_SOURCE=absent';fi
if test -e /opt/natural-automation/data/steward.db; then echo 'HOST_STEWARD_DATABASE=present';else echo 'HOST_STEWARD_DATABASE=absent';fi
if test -x /usr/local/sbin/ha-steward-pve-wrapper; then echo 'HOST_STEWARD_WRAPPER=present';else echo 'HOST_STEWARD_WRAPPER=absent';fi
printf 'HOST_STEWARD_STATUS_HTTP='
curl -sS --max-time 8 -o /tmp/jns-steward-audit-status.$.json -w '%{http_code}\n' http://127.0.0.1:8099/api/status || true
if test -s /tmp/jns-steward-audit-status.$.json; then
 python3 - /tmp/jns-steward-audit-status.$.json <<'PY'
import json,sys
try:
 d=json.load(open(sys.argv[1]))
 print('HOST_STEWARD_RUNTIME',json.dumps({'ok':d.get('ok'),'apply_enabled':d.get('apply_enabled'),'target_role':(d.get('target') or {}).get('role'),'target_vmid':(d.get('target') or {}).get('vmid')}))
except Exception as e:print('HOST_STEWARD_RUNTIME_UNREADABLE',type(e).__name__)
PY
fi
rm -f /tmp/jns-steward-audit-status.$.json
printf 'HOST_HA_GENERAL_API_HTTP='
curl -sS --max-time 8 -o /dev/null -w '%{http_code}\n' http://ha-general.home.arpa:8123/api/ || true
printf "HA_GENERAL_VM905="
qm status 905 2>&1 | sed -n "1p"
echo 'JNS_STEWARD_AUDIT_END'
NODEB
