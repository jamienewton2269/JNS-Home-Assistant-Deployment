#!/usr/bin/env bash
# ONE-TIME LOCAL NODE C ROOT INSTALLER.
set -Eeuo pipefail

SRC_ROOT="$(cd "$(dirname "$0")" && pwd)"
CURRENT=/usr/local/sbin/jns-gateway-exec
BASE=/usr/local/sbin/jns-gateway-exec.base
PKG_HELPER=/usr/local/libexec/jns-gateway-ha-package-install
NET_HELPER=/usr/local/libexec/jns-gateway-ha-network-identity-install

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
install -o root -g root -m 0755 "$SRC_ROOT/jns-gateway-exec-wrapper-v2.sh" "$CURRENT"

echo "JNS trusted gateway Network Identity extension installed"
echo "executor=$CURRENT"
echo "network_identity_handler=$NET_HELPER"
