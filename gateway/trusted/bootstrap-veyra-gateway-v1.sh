#!/usr/bin/env bash
set -Eeuo pipefail

[ "$(id -u)" -eq 0 ] || {
  echo "Run this once as root on Node C." >&2
  exit 77
}

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
HANDLER="$ROOT/gateway/trusted/veyra-gateway-handler-v1.py"
WRAPPER="$ROOT/gateway/trusted/jns-gateway-exec-wrapper-v3.sh"
BUILDER="$ROOT/gateway/trusted/veyra-build-v092.sh"
PXE="$ROOT/gateway/trusted/veyra-pxe-v092.sh"
CURRENT=/usr/local/sbin/jns-gateway-exec
TARGET=/usr/local/libexec/jns-gateway-veyra
BUILD_TARGET=/usr/local/libexec/jns-veyra-build-v092
PXE_TARGET=/usr/local/libexec/jns-veyra-pxe-v092

[ -f "$HANDLER" ] || { echo "Missing $HANDLER" >&2; exit 66; }
[ -f "$WRAPPER" ] || { echo "Missing $WRAPPER" >&2; exit 66; }
[ -f "$BUILDER" ] || { echo "Missing $BUILDER" >&2; exit 66; }
[ -f "$PXE" ] || { echo "Missing $PXE" >&2; exit 66; }
[ -x "$CURRENT" ] || { echo "Missing current trusted gateway executor" >&2; exit 78; }

PYTHONDONTWRITEBYTECODE=1 python3 - <<PY
import ast, pathlib
ast.parse(pathlib.Path("$HANDLER").read_text(encoding="utf-8"))
PY
bash -n "$WRAPPER"
bash -n "$BUILDER"
bash -n "$PXE"

install -d -o root -g root -m 0755 /usr/local/libexec
cp -a "$CURRENT" "$CURRENT.pre-veyra"
install -o root -g root -m 0755 "$HANDLER" "$TARGET"
install -o root -g root -m 0755 "$BUILDER" "$BUILD_TARGET"
install -o root -g root -m 0755 "$PXE" "$PXE_TARGET"
install -o root -g root -m 0755 "$WRAPPER" "$CURRENT"

test -x "$TARGET"
test -x "$BUILD_TARGET"
test -x "$PXE_TARGET"
test -x "$CURRENT"

echo "=== VEYRA GATEWAY BOOTSTRAP COMPLETE ==="
sha256sum "$TARGET" "$BUILD_TARGET" "$PXE_TARGET" "$CURRENT"
echo "backup=$CURRENT.pre-veyra"
