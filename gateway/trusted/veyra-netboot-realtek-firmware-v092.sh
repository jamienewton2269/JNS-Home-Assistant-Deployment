#!/usr/bin/env bash
# Add exact Realtek firmware to INDEPENDENT Debian netboot initrd ONLY.
# Never touch canonical Veyra V path, iPXE menu, or Debian kernel.
set -Eeuo pipefail
test "$(id -u)" -eq 0 || { echo 'Run as root on Node C'; exit 77; }
D=/srv/veyra-pxe/http/veyra/v0.9.2-netboot
V=/srv/veyra-pxe/http/veyra/v0.9.2
M=/srv/veyra-pxe/http/autoexec.ipxe
T=/srv/veyra-pxe/tftp/autoexec.ipxe
test -s "$D/initrd.gz" && test -s "$D/vmlinuz" && test -s "$M"
test "$(sha256sum "$V/vmlinuz" | cut -d' ' -f1)" = 2b2358b37674d2505350528875bb17afae2a36522a9e8a9417eaca65a7da0e08
test "$(sha256sum "$V/initrd.gz" | cut -d' ' -f1)" = 8de544ab627ab794504c530c82de621814386b5b67a492f1e3133390c47ea933
BEFORE=$(sha256sum "$M" "$T" "$V/vmlinuz" "$V/initrd.gz" "$D/vmlinuz")
W=$(mktemp -d /tmp/veyra-realtek-XXXXXXXX)
trap 'rm -rf "$W"' EXIT
mkdir "$W/root"
# Download Debian Trixie firmware-realtek, using Debian's published SHA256.
URL=https://deb.debian.org/debian/pool/non-free-firmware/f/firmware-nonfree/firmware-realtek_20250410-2_all.deb
curl -fsSL --retry 2 --connect-timeout 10 --max-time 90 "$URL" -o "$W/firmware-realtek.deb"
echo '925755a9b0891c7dc39bbb73d28ab8f7193d37303b5022e8bc9d458b9b4aaa4e  '"$W"'/firmware-realtek.deb' | sha256sum -c -
mkdir "$W/pkg"
dpkg-deb -x "$W/firmware-realtek.deb" "$W/pkg"
test -s "$W/pkg/usr/lib/firmware/rtl_nic/rtl8106e-1.fw"
cp "$W/pkg/usr/lib/firmware/rtl_nic/rtl8106e-1.fw" "$W/rtl8106e-1.fw"
test "$(wc -c < "$W/rtl8106e-1.fw")" -eq 1856
# Rebuild one standard initramfs, retaining ownership, symlinks and special device nodes.
(cd "$W/root"; gzip -dc "$D/initrd.gz" | cpio --extract --make-directories --unconditional --quiet)
test -c "$W/root/dev/console" && test -c "$W/root/dev/null" || { echo 'STOP: unpacked initrd missing device nodes'; exit 66; }
mkdir -p "$W/root/usr/lib/firmware/rtl_nic" "$W/root/lib/firmware/rtl_nic"
install -m 0644 "$W/rtl8106e-1.fw" "$W/root/usr/lib/firmware/rtl_nic/rtl8106e-1.fw"
install -m 0644 "$W/rtl8106e-1.fw" "$W/root/lib/firmware/rtl_nic/rtl8106e-1.fw"
(cd "$W/root"; find . -print0 | cpio --null --format=newc --create --quiet | gzip -9 > "$W/initrd.gz")
gzip -t "$W/initrd.gz"
mkdir "$W/verify"
(cd "$W/verify"; gzip -dc "$W/initrd.gz" | cpio --extract --make-directories --quiet)
cmp "$W/rtl8106e-1.fw" "$W/verify/usr/lib/firmware/rtl_nic/rtl8106e-1.fw"
test -c "$W/verify/dev/console"
test -c "$W/verify/dev/null"
BACK=/srv/veyra-pxe/backups/veyra-netboot-realtek-$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p "$BACK"
cp -a "$D/initrd.gz" "$BACK/initrd.gz"
printf '%s\n' "$BEFORE" > "$BACK/protected-boot-sha256.txt"
install -m 0644 "$W/initrd.gz" "$D/initrd.gz.next"
mv -f "$D/initrd.gz.next" "$D/initrd.gz"
if [[ "$BEFORE" != "$(sha256sum "$M" "$T" "$V/vmlinuz" "$V/initrd.gz" "$D/vmlinuz")" ]] || ! curl -fsS -o /dev/null "http://127.0.0.1:8098/veyra/v0.9.2-netboot/initrd.gz"; then
 cp -a "$BACK/initrd.gz" "$D/initrd.gz"
 echo 'STOP: baseline or HTTP verification failed; N initrd rolled back'; exit 80
fi
echo "VEYRA_NETBOOT_REALTEK_FIRMWARE_PUBLISHED"
echo "FIRMWARE=rtl_nic/rtl8106e-1.fw"
echo "PROTECTED_PXE_UNCHANGED"
echo "ROLLBACK=$BACK"
sha256sum "$D/initrd.gz"
