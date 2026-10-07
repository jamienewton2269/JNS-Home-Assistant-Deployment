#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HTML="$REPO_ROOT/ha_infrastructure_launchpad/index.html"
NODE_B="nodeb"
VMID="905"
HA_IP="10.10.10.223"
HA_ROOT="/mnt/data/supervisor/homeassistant"
TARGET="$HA_ROOT/www/jns-infrastructure/index.html"
CFG="$HA_ROOT/configuration.yaml"
STAMP="$(date +%Y%m%dT%H%M%S)"

[[ -s "$HTML" ]] || { echo "Missing launchpad HTML: $HTML" >&2; exit 2; }

echo "=== JNS HA-General Infrastructure Launchpad deployment ==="
echo "target=HA-General vmid=$VMID ip=$HA_IP"

HTML_B64="$(base64 -w0 "$HTML")"
HTML_SHA="$(sha256sum "$HTML" | awk '{print $1}')"

timeout 240s ssh -o BatchMode=yes "$NODE_B"   "VMID='$VMID' HA_IP='$HA_IP' HA_ROOT='$HA_ROOT' TARGET='$TARGET' CFG='$CFG' STAMP='$STAMP' HTML_SHA='$HTML_SHA' HTML_B64='$HTML_B64' bash -s" <<'NODEB'
set -Eeuo pipefail

guest() {
  local cmd="$1"
  local seconds="${2:-120}"
  qm guest exec "$VMID" --timeout "$seconds" -- /bin/bash -lc "$cmd"
}

echo "[1/7] Confirm VM905 is running"
qm status "$VMID" | grep -q 'status: running'

echo "[2/7] Back up configuration and existing launchpad"
guest "cp -a '$CFG' '$CFG.jns-launchpad-$STAMP.bak'; mkdir -p '$HA_ROOT/www/jns-infrastructure'; if [ -f '$TARGET' ]; then cp -a '$TARGET' '$TARGET.jns-launchpad-$STAMP.bak'; fi" >/dev/null

rollback() {
  echo "ROLLBACK: restoring Home Assistant configuration" >&2
  guest "cp -a '$CFG.jns-launchpad-$STAMP.bak' '$CFG'; if [ -f '$TARGET.jns-launchpad-$STAMP.bak' ]; then cp -a '$TARGET.jns-launchpad-$STAMP.bak' '$TARGET'; else rm -f '$TARGET'; fi" >/dev/null 2>&1 || true
}
trap 'rc=$?; if [ "$rc" -ne 0 ]; then rollback; fi; exit "$rc"' EXIT

echo "[3/7] Install static launchpad"
guest "printf '%s' '$HTML_B64' | base64 -d > '$TARGET.jns-new'; test -s '$TARGET.jns-new'; mv -f '$TARGET.jns-new' '$TARGET'; chmod 0644 '$TARGET'" >/dev/null

ACTUAL_SHA="$(guest "sha256sum '$TARGET' | cut -d' ' -f1" | sed -n 's/.*out-data":"\([^"\\]*\).*/\1/p' | tr -d '\\nr' | tail -n1)"
if [ -z "$ACTUAL_SHA" ]; then
  ACTUAL_SHA="$(guest "sha256sum '$TARGET'" | grep -oE '[0-9a-f]{64}' | head -n1)"
fi
[ "$ACTUAL_SHA" = "$HTML_SHA" ] || { echo "HTML integrity mismatch expected=$HTML_SHA actual=$ACTUAL_SHA" >&2; exit 43; }

echo "[4/7] Add Home Assistant sidebar panel"
guest "if grep -q '^  jns_infrastructure:' '$CFG'; then
  echo 'panel already present';
elif grep -q '^panel_iframe:' '$CFG'; then
  sed -i '/^panel_iframe:/a\\  jns_infrastructure:\\n    title: Infrastructure\\n    icon: mdi:server-network\\n    url: /local/jns-infrastructure/index.html\\n    require_admin: true' '$CFG';
else
  printf '\\npanel_iframe:\\n  jns_infrastructure:\\n    title: Infrastructure\\n    icon: mdi:server-network\\n    url: /local/jns-infrastructure/index.html\\n    require_admin: true\\n' >> '$CFG';
fi" >/dev/null

echo "[5/7] Validate Home Assistant configuration"
guest "ha core check" 150

echo "[6/7] Restart Home Assistant Core"
guest "ha core restart" 20 >/dev/null || true

echo "[7/7] Verify HA and launchpad endpoint"
ok=0
for n in $(seq 1 45); do
  code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 4 "http://$HA_IP/local/jns-infrastructure/index.html" || true)"
  if [ "$code" = "200" ]; then
    ok=1
    echo "launchpad_http=200 attempt=$n"
    break
  fi
  sleep 2
done
[ "$ok" -eq 1 ] || { echo "Launchpad endpoint failed to return HTTP 200" >&2; exit 44; }

trap - EXIT
echo "JNS_INFRASTRUCTURE_LAUNCHPAD_DEPLOY_OK"
echo "url=http://$HA_IP/local/jns-infrastructure/index.html"
echo "sidebar=Infrastructure"
echo "sha256=$HTML_SHA"
NODEB
