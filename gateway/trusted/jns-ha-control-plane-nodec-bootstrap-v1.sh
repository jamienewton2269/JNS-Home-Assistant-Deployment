#!/usr/bin/env bash
# JNS HA control-plane bootstrap - staged on Node C, no implicit destructive actions.
set -Eeuo pipefail
umask 077
ROOT=/opt/jns-ha-control-plane
PRIMARY=10.10.10.220
GENERAL=10.10.10.223
log(){ printf '[%s] %s\n' "$(date -Is)" "$*"; }
die(){ log "ERROR: $*"; exit 1; }
[[ $(id -u) -eq 0 ]] || die "Run as root on Node C"
command -v curl >/dev/null || die "curl required"
mkdir -p "$ROOT"/{reports,packages,backups}
REPORT="$ROOT/reports/preflight-$(date +%Y%m%dT%H%M%S).txt"
{
 echo "JNS HA Control Plane - Node C preflight"; date -Is; hostname
 for pair in "HA902 $PRIMARY" "HA905 $GENERAL"; do
   read -r name host <<< "$pair"
   printf '%s %s HTTP: ' "$name" "$host"
   curl --silent --show-error --connect-timeout 3 --max-time 8 -o /dev/null -w '%{http_code}\n' "http://$host:8123/" || true
   printf '%s SSH 22: ' "$name"
   if timeout 4 bash -c 'exec 3<>/dev/tcp/"$1"/22' bash "$host" 2>/dev/null; then echo reachable; else echo unavailable; fi
 done
} | tee "$REPORT"
cat > "$ROOT/README.txt" <<'EOF'
JNS HA902 Primary Lite control-plane rollout
Architecture: HA902 (10.10.10.220:8123) is the sole client-facing dashboard.
HA905 (10.10.10.223:8123) remains owner of General devices and automations.
Do not activate HA900/HA901, VM100 or Node B's VM900 recovery copy.
Remote Home-Assistant must be installed on BOTH HA902 and HA905.
https://github.com/custom-components/remote_homeassistant
On HA905 configuration.yaml add, ONLY if not already configured:
remote_homeassistant:
  instances: []
After config validation, restart HA905.
In HA905 profile create a long-lived access token; store it securely, not in Git or
the Node C deployment output. On HA902 install same integration and add via UI:
Settings -> Devices & services -> Add integration -> Remote Home-Assistant
Host: 10.10.10.223, Port: 8123, Secure: no (LAN HTTP), Token: HA905 token.
Select needed entities; use an optional namespace prefix if conflicts exist.
Test entity state, light/switch toggles, automation status and automation triggers.
Remote automation editing remains on the owning HA905 instance; build inventory links.
Before any HA configuration changes, take backups, check live file paths, and validate
both systems. No HA files are modified by this Node C bootstrap.
EOF
log "Preflight report: $REPORT"
log "Instructions: $ROOT/README.txt"
log "Bootstrap finished; Home Assistant configuration NOT modified."
