#!/usr/bin/env bash
set -Eeuo pipefail

[ "$(id -u)" -eq 0 ] || {
  echo "Run this once as root on Node C." >&2
  exit 77
}

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
HANDLER="$ROOT/gateway/trusted/veyra-gateway-handler-v1.py"
WRAPPER="$ROOT/gateway/trusted/jns-gateway-exec-wrapper-v3.sh"
CURRENT=/usr/local/sbin/jns-gateway-exec
TARGET=/usr/local/libexec/jns-gateway-veyra

[ -f "$HANDLER" ] || { echo "Missing $HANDLER" >&2; exit 66; }
[ -f "$WRAPPER" ] || { echo "Missing $WRAPPER" >&2; exit 66; }
[ -x "$CURRENT" ] || { echo "Missing current trusted gateway executor" >&2; exit 78; }

python3 -m py_compile "$HANDLER"
bash -n "$WRAPPER"

install -d -o root -g root -m 0755 /usr/local/libexec
cp -a "$CURRENT" "$CURRENT.pre-veyra"
install -o root -g root -m 0755 "$HANDLER" "$TARGET"
install -o root -g root -m 0755 "$WRAPPER" "$CURRENT"

test -x "$TARGET"
test -x "$CURRENT"

echo "=== VEYRA GATEWAY BOOTSTRAP COMPLETE ==="
sha256sum "$TARGET" "$CURRENT"
echo "backup=$CURRENT.pre-veyra"
