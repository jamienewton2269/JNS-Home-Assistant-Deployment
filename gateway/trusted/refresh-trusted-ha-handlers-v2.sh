#!/usr/bin/env bash
set -Eeuo pipefail

[ "$(id -u)" -eq 0 ] || { echo "Run on Node C as root" >&2; exit 77; }

SRC_ROOT="$(cd "$(dirname "$0")" && pwd)"
CURRENT=/usr/local/sbin/jns-gateway-exec
BASE=/usr/local/sbin/jns-gateway-exec.base

install -d -o root -g root -m 0755 /usr/local/libexec

[ -x "$BASE" ] || {
  [ -x "$CURRENT" ] || { echo "Missing current trusted executor" >&2; exit 78; }
  cp -a "$CURRENT" "$BASE"
  chown root:root "$BASE"
  chmod 0755 "$BASE"
}

install -o root -g root -m 0755 "$SRC_ROOT/ha-package-install-handler-v1.sh" /usr/local/libexec/jns-gateway-ha-package-install
install -o root -g root -m 0755 "$SRC_ROOT/ha-network-identity-install-handler-v1.sh" /usr/local/libexec/jns-gateway-ha-network-identity-install
install -o root -g root -m 0755 "$SRC_ROOT/ha-tuya-local-event-wake-patch-handler-v1.sh" /usr/local/libexec/jns-gateway-ha-tuya-local-event-wake-patch
install -o root -g root -m 0755 "$SRC_ROOT/gateway-bridge-selftest-handler-v1.sh" /usr/local/libexec/jns-gateway-bridge-selftest
install -o root -g root -m 0755 "$SRC_ROOT/jns-gateway-exec-wrapper-v2.sh" "$CURRENT"

echo "=== TRUSTED HANDLERS REFRESHED ==="
sha256sum   "$CURRENT"   /usr/local/libexec/jns-gateway-ha-package-install   /usr/local/libexec/jns-gateway-ha-network-identity-install   /usr/local/libexec/jns-gateway-ha-tuya-local-event-wake-patch   /usr/local/libexec/jns-gateway-bridge-selftest
