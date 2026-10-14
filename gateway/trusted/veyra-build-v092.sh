#!/usr/bin/env bash
set -Eeuo pipefail

WORK=/root/veyra-v0.9
PAYLOAD=$WORK/source071/veyra
BASE_ISO=$WORK/Veyra-AutoInstall-v0.9.1.iso
OUT=$WORK/Veyra-AutoInstall-v0.9.2.iso
TMP=$WORK/.Veyra-AutoInstall-v0.9.2.tmp.iso
SUM=$WORK/Veyra-AutoInstall-v0.9.2.sha256
SIG=$WORK/Veyra-AutoInstall-v0.9.2.sha256.sig
KEY=/root/.jns/veyra-signing/ed25519.key
PUB=/root/.jns/veyra-signing/ed25519.pub

echo "=== VEYRA V0.9.2 BUILD ==="
date -Is

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
print('SOURCE_VALIDATION_OK')
PY

find "$PAYLOAD" -type d -name __pycache__ -prune -exec rm -rf {} +
find "$PAYLOAD" -type f -name '*.pyc' -delete

rm -f "$TMP"
xorriso   -indev "$BASE_ISO"   -outdev "$TMP"   -boot_image any replay   -volid VEYRA_AUTO_092   -update_r "$PAYLOAD" /veyra   -commit

mv -f "$TMP" "$OUT"
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
