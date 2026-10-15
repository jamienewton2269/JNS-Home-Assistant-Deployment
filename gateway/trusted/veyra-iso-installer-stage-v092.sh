#!/usr/bin/env bash
# Read-only against the live PXE tree. Rebuild a candidate from the ISO/CD initrd.
set -Eeuo pipefail
SRC=/srv/veyra-pxe/http/veyra/v0.9.2
OUT="${1:?staging output directory required}"
[[ "$OUT" == /tmp/veyra-v092-stage-* ]] || { echo 'STOP: staging must be under /tmp/veyra-v092-stage-*' >&2; exit 64; }
mkdir -p "$OUT" "$OUT/work" "$OUT/unpack" "$OUT/nic"
[[ "$(sha256sum "$SRC/vmlinuz-cd" | cut -d' ' -f1)" == 2b2358b37674d2505350528875bb17afae2a36522a9e8a9417eaca65a7da0e08 ]]
[[ "$(sha256sum "$SRC/initrd-cd.gz" | cut -d' ' -f1)" == 8de544ab627ab794504c530c82de621814386b5b67a492f1e3133390c47ea933 ]]
echo '=== PRESERVE ISO-MATCHED KERNEL ==='
cp -- "$SRC/vmlinuz-cd" "$OUT/vmlinuz"
URL='https://security.debian.org/debian-security/pool/updates/main/l/linux-signed-amd64/nic-modules-6.12.107%2Bdeb13-amd64-di_6.12.107-1_amd64.udeb'
curl -fsSL --retry 2 --connect-timeout 15 --max-time 120 "$URL" -o "$OUT/work/nic.udeb"
echo "195b7eabe935648a0fa858caea2d6d59c51e0fbda99837e5020c6186c9dbca51  $OUT/work/nic.udeb" | sha256sum -c -
dpkg-deb -x "$OUT/work/nic.udeb" "$OUT/nic"
test -f "$OUT/nic/lib/modules/6.12.107+deb13-amd64/kernel/drivers/net/ethernet/realtek/r8169.ko.xz"
echo '=== INSPECT ORIGINAL ISO INSTALLER WITHOUT DEVICE-NODE RECREATION ==='
(
  cd "$OUT/unpack"
  gzip -dc "$SRC/initrd-cd.gz" | cpio -idmu --quiet --no-preserve-owner -f 'dev/console' 'dev/null' || status=$?
  # GNU cpio returns nonzero for excluded device nodes; confirm its useful files.
  test -d usr/lib/modules/6.12.107+deb13-amd64
)
mkdir -p "$OUT/unpack/usr/lib/modules"
cp -an "$OUT/nic/lib/modules/." "$OUT/unpack/usr/lib/modules/"
test -f "$OUT/unpack/usr/lib/modules/6.12.107+deb13-amd64/kernel/drivers/net/ethernet/realtek/r8169.ko.xz"
if command -v depmod >/dev/null; then
  depmod -b "$OUT/unpack" '6.12.107+deb13-amd64'
else
  echo 'STOP: depmod unavailable; refusing unverifiable module dependencies' >&2; exit 65
fi
echo '=== CREATE MODULE-ONLY CPIO OVERLAY, KEEP BASE INTACT ==='
mkdir -p "$OUT/overlay/usr/lib/modules/6.12.107+deb13-amd64/kernel/drivers/net/ethernet/realtek"
cp "$OUT/nic/lib/modules/6.12.107+deb13-amd64/kernel/drivers/net/ethernet/realtek/r8169.ko.xz" "$OUT/overlay/usr/lib/modules/6.12.107+deb13-amd64/kernel/drivers/net/ethernet/realtek/"
for f in modules.dep modules.dep.bin modules.alias modules.alias.bin modules.symbols modules.symbols.bin; do
  test -f "$OUT/unpack/usr/lib/modules/6.12.107+deb13-amd64/$f" || continue
  cp "$OUT/unpack/usr/lib/modules/6.12.107+deb13-amd64/$f" "$OUT/overlay/usr/lib/modules/6.12.107+deb13-amd64/$f"
done
grep -q 'r8169.ko' "$OUT/overlay/usr/lib/modules/6.12.107+deb13-amd64/modules.dep"
(cd "$OUT/overlay"; find . -print0 | cpio --null --format=newc -o 2>/dev/null | gzip -9 > "$OUT/overlay.gz")
cp "$SRC/initrd-cd.gz" "$OUT/initrd.gz"
cat "$OUT/overlay.gz" >> "$OUT/initrd.gz"
gzip -t "$OUT/initrd.gz"
gzip -dc "$OUT/overlay.gz" | cpio -it 2>/dev/null > "$OUT/overlay.list"
grep -Fq 'usr/lib/modules/6.12.107+deb13-amd64/kernel/drivers/net/ethernet/realtek/r8169.ko.xz' "$OUT/overlay.list"
sha256sum "$OUT/vmlinuz" "$OUT/initrd.gz" "$OUT/overlay.gz"
echo 'VEYRA_ISO_MATCHED_NIC_CANDIDATE_STAGED_ONLY'
