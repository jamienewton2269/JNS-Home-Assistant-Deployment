#!/usr/bin/env bash
set -Eeuo pipefail

WORK=/root/veyra-v0.9
SOURCE_ROOT=$WORK/source071
PAYLOAD=$SOURCE_ROOT/veyra
BASE_ISO=$WORK/Veyra-AutoInstall-v0.9.1.iso
OUT=$WORK/Veyra-AutoInstall-v0.9.2.iso
TMP=$WORK/.Veyra-AutoInstall-v0.9.2.tmp.iso
SUM=$WORK/Veyra-AutoInstall-v0.9.2.sha256
SIG=$WORK/Veyra-AutoInstall-v0.9.2.sha256.sig
KEY=/root/.jns/veyra-signing/ed25519.key
PUB=/root/.jns/veyra-signing/ed25519.pub

echo "=== VEYRA V0.9.2 BUILD ==="
date -Is

test -d "$SOURCE_ROOT"
test -d "$PAYLOAD"
test -f "$BASE_ISO"
command -v xorriso >/dev/null
command -v openssl >/dev/null

python3 -m compileall -q "$PAYLOAD/veyra"
python3 - <<'PY'
import json
from pathlib import Path
base=Path('/root/veyra-v0.9/source071/veyra')
json.loads((base/'browser-extension/manifest.json').read_text())
app=(base/'veyra/app.py').read_text()
if '/api/admin-console/io' in app:
    raise SystemExit('obsolete web shell route present')
ver=(base/'veyra/__init__.py').read_text()
if '0.9.2' not in ver:
    raise SystemExit('source version is not 0.9.2')
view=(base/'veyra/view.py').read_text()
for marker in ('YOUR PROGRAMMES','My Programmes','Services'):
    if marker not in view:
        raise SystemExit(f'missing UI marker: {marker}')
print('SOURCE_VALIDATION_OK')
PY

find "$PAYLOAD" -type d -name __pycache__ -prune -exec rm -rf {} +
find "$PAYLOAD" -type f -name '*.pyc' -delete

rm -f "$TMP"
xorriso   -indev "$BASE_ISO"   -outdev "$TMP"   -boot_image any replay   -volid VEYRA_AUTO_092   -update_r "$SOURCE_ROOT" /   -commit

mv -f "$TMP" "$OUT"

VERIFY_DIR="$(mktemp -d)"
trap 'rm -rf "$VERIFY_DIR"' EXIT
xorriso -osirrox on -indev "$OUT" -extract /veyra/veyra/view.py "$VERIFY_DIR/view.py" >/dev/null 2>&1
xorriso -osirrox on -indev "$OUT" -extract /veyra/veyra/__init__.py "$VERIFY_DIR/__init__.py" >/dev/null 2>&1
grep -q 'YOUR PROGRAMMES' "$VERIFY_DIR/view.py"
grep -q 'My Programmes' "$VERIFY_DIR/view.py"
grep -q 'Services' "$VERIFY_DIR/view.py"
grep -q '0.9.2' "$VERIFY_DIR/__init__.py"
xorriso -indev "$OUT" -ls /preseed.cfg >/dev/null 2>&1
xorriso -indev "$OUT" -ls /install.amd/vmlinuz >/dev/null 2>&1
xorriso -indev "$OUT" -ls /install.amd/initrd.gz >/dev/null 2>&1
echo "ISO_PAYLOAD_VALIDATION_OK"

sha256sum "$OUT" > "$SUM"

signed=false
if [[ -f "$KEY" && -f "$PUB" ]]; then
  openssl pkeyutl -sign -inkey "$KEY" -rawin -in "$SUM" -out "$SIG"
  openssl pkeyutl -verify -pubin -inkey "$PUB" -rawin -in "$SUM" -sigfile "$SIG"
  signed=true
fi

echo "=== BOOT ENTRIES ==="
xorriso -indev "$OUT" -report_el_torito plain 2>/dev/null | sed -n '1,120p'
echo "=== OUTPUT ==="
cat "$SUM"
echo "signed=$signed"
echo "VEYRA_V092_BUILD_OK"
