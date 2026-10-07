#!/usr/bin/env bash
# ONE-TIME LOCAL NODE C ROOT INSTALLER.
set -Eeuo pipefail

SRC_ROOT="$(cd "$(dirname "$0")" && pwd)"
CURRENT=/usr/local/sbin/jns-gateway-exec
BASE=/usr/local/sbin/jns-gateway-exec.base
PKG_HELPER=/usr/local/libexec/jns-gateway-ha-package-install
NET_HELPER=/usr/local/libexec/jns-gateway-ha-network-identity-install
TUYA_WAKE_HELPER=/usr/local/libexec/jns-gateway-ha-tuya-local-event-wake-patch

[ "$(id -u)" -eq 0 ] || { echo "Run locally on Node C as root" >&2; exit 77; }
[ -x "$CURRENT" ] || { echo "Missing $CURRENT" >&2; exit 78; }

install -d -o root -g root -m 0755 /usr/local/libexec

if [ ! -e "$BASE" ]; then
  cp -a "$CURRENT" "$BASE"
  chown root:root "$BASE"
  chmod 0755 "$BASE"
fi

if [ -f "$SRC_ROOT/ha-package-install-handler-v1.sh" ]; then
  install -o root -g root -m 0755 "$SRC_ROOT/ha-package-install-handler-v1.sh" "$PKG_HELPER"
fi

install -o root -g root -m 0755 "$SRC_ROOT/ha-network-identity-install-handler-v1.sh" "$NET_HELPER"

if [ -f "$SRC_ROOT/ha-tuya-local-event-wake-patch-handler-v1.sh" ]; then
  install -o root -g root -m 0755 "$SRC_ROOT/ha-tuya-local-event-wake-patch-handler-v1.sh" "$TUYA_WAKE_HELPER"
fi

install -o root -g root -m 0755 "$SRC_ROOT/jns-gateway-exec-wrapper-v2.sh" "$CURRENT"

echo "JNS trusted gateway extension installed"
echo "executor=$CURRENT"
echo "network_identity_handler=$NET_HELPER"
echo "tuya_event_wake_handler=$TUYA_WAKE_HELPER"


# LIVE WRAPPER VERIFICATION
grep -q 'ha_network_identity_install)' "$CURRENT" || {
  echo "ERROR: live executor does not contain ha_network_identity_install" >&2
  exit 79
}
[ -x "$NET_HELPER" ] || {
  echo "ERROR: network identity helper is not executable" >&2
  exit 79
}
echo "live_network_identity_allowlist=OK"
sha256sum "$CURRENT" "$NET_HELPER"
