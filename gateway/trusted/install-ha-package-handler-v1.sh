#!/usr/bin/env bash
# ONE-TIME LOCAL NODE C ROOT INSTALLER.
# This does not execute HA deployment commands. It only extends the trusted
# root-owned dispatcher with the narrowly scoped ha_package_install handler.
set -Eeuo pipefail

SRC_ROOT="$(cd "$(dirname "$0")" && pwd)"
CURRENT=/usr/local/sbin/jns-gateway-exec
BASE=/usr/local/sbin/jns-gateway-exec.base
HELPER=/usr/local/libexec/jns-gateway-ha-package-install

[ "$(id -u)" -eq 0 ] || { echo "Run locally on Node C as root" >&2; exit 77; }
[ -x "$CURRENT" ] || { echo "Missing $CURRENT" >&2; exit 78; }

install -d -o root -g root -m 0755 /usr/local/libexec

if [ ! -e "$BASE" ]; then
  cp -a "$CURRENT" "$BASE"
  chown root:root "$BASE"
  chmod 0755 "$BASE"
fi

install -o root -g root -m 0755 "$SRC_ROOT/ha-package-install-handler-v1.sh" "$HELPER"
install -o root -g root -m 0755 "$SRC_ROOT/jns-gateway-exec-wrapper-v1.sh" "$CURRENT"

"$CURRENT" --help >/dev/null 2>&1 || true

echo "JNS trusted gateway extension installed"
echo "base_executor=$BASE"
echo "package_handler=$HELPER"
echo "executor=$CURRENT"
