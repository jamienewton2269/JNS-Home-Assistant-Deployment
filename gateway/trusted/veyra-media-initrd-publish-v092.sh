#!/usr/bin/env bash
# Install only the Veyra Debian media-recovery initrd; never alter PXE transport or kernel.
set -Eeuo pipefail
[[ $(id -u) -eq 0 ]] || { echo 'STOP: run as root on Node C' >&2; exit 77; }
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
ROOT=/srv/veyra-pxe
D=$ROOT/http/veyra/v0.9.2
MENU=$ROOT/http/autoexec.ipxe
BUILDER=$REPO/gateway/trusted/veyra-media-initrd-stage-v092.sh
test -f "$MENU" && test -f "$D/initrd.gz" && test -f "$D/vmlinuz"
test -x "$BUILDER" || bash -n "$BUILDER"
grep -Fq 'kernel ${base}/vmlinuz initrd=initrd.magic' "$MENU"
grep -Fq 'initrd --name initrd.gz ${base}/initrd.gz' "$MENU"
! grep -Fq 'sanboot ' "$MENU"
test "$(sha256sum "$D/vmlinuz" | cut -d' ' -f1)" = 2b2358b37674d2505350528875bb17afae2a36522a9e8a9417eaca65a7da0e08
BEFORE_MENU="$(sha256sum "$MENU" | cut -d' ' -f1)"
BEFORE_KERNEL="$(sha256sum "$D/vmlinuz" | cut -d' ' -f1)"
WORK=$(mktemp -d /tmp/veyra-media-publish-XXXXXXXX)
trap 'rm -rf "$WORK"' EXIT
bash "$BUILDER" "$WORK"
test -s "$WORK/initrd.gz"
gzip -t "$WORK/initrd.gz"
BCK="$ROOT/backups/veyra-media-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$BCK"
cp -a "$D/initrd.gz" "$BCK/initrd.gz"
cp -a "$MENU" "$BCK/autoexec.ipxe"
cp -a "$D/vmlinuz" "$BCK/vmlinuz"
echo "VEYRA_MEDIA_ROLLBACK_DIR=$BCK"
# Atomic swap only the initrd; all other PXE files and services remain untouched.
install -m 0644 "$WORK/initrd.gz" "$D/initrd.gz.veyra-next"
mv -f "$D/initrd.gz.veyra-next" "$D/initrd.gz"
if ! gzip -t "$D/initrd.gz" || \
   [[ "$(sha256sum "$MENU" | cut -d' ' -f1)" != "$BEFORE_MENU" ]] || \
   [[ "$(sha256sum "$D/vmlinuz" | cut -d' ' -f1)" != "$BEFORE_KERNEL" ]]; then
  cp -a "$BCK/initrd.gz" "$D/initrd.gz"
  echo 'STOP: post-publication guard failed; initrd rolled back' >&2
  exit 1
fi
curl -fsSI http://127.0.0.1:8098/veyra/v0.9.2/initrd.gz | grep -q '200 OK' || {
  cp -a "$BCK/initrd.gz" "$D/initrd.gz"
  echo 'STOP: HTTP check failed; initrd rolled back' >&2
  exit 1
}
echo "VEYRA_MEDIA_INITRD_SHA256=$(sha256sum "$D/initrd.gz" | cut -d' ' -f1)"
echo 'VEYRA_MEDIA_ONLY_INITRD_PUBLISHED'
echo 'VEYRA_PXE_BOOT_CHAIN_UNCHANGED'
