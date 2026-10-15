#!/usr/bin/env bash
# Stage only: preserve every live PXE and ISO file. Never touch laptop disk.
set -Eeuo pipefail
BASE=/srv/veyra-pxe/http/veyra/v0.9.2
DEST="${1:?output directory required}"
[[ $(id -u) -eq 0 ]] || { echo 'STOP: rebuilding ISO initrd requires root to preserve /dev/console and /dev/null' >&2; exit 77; }
[[ "$DEST" == /tmp/veyra-media-*-* ]] || { echo 'STOP: need /tmp/veyra-media-*-*' >&2; exit 64; }
mkdir -p "$DEST"/{original,overlay,extract}
sha256sum "$BASE/vmlinuz-cd" "$BASE/initrd-cd.gz"
echo '2b2358b37674d2505350528875bb17afae2a36522a9e8a9417eaca65a7da0e08  '"$BASE"'/vmlinuz-cd' | sha256sum -c -
echo '8de544ab627ab794504c530c82de621814386b5b67a492f1e3133390c47ea933  '"$BASE"'/initrd-cd.gz' | sha256sum -c -
echo '53e31c84dc0613773e1224215e03004423d3daaaf5ff6cbd518dd1f17f15e246  '"$BASE"'/Veyra-AutoInstall-v0.9.2.iso' | sha256sum -c -
(
 cd "$DEST/original"
 gzip -dc "$BASE/initrd-cd.gz" | cpio -idmu --quiet
)
ISO="$BASE/Veyra-AutoInstall-v0.9.2.iso"
NIC=/pool/main/l/linux-signed-amd64/nic-modules-6.12.107+deb13-amd64-di_6.12.107-1_amd64.udeb
xorriso -osirrox on -indev "$ISO" -extract "$NIC" "$DEST/extract/nic.udeb" >/dev/null 2>&1
dpkg-deb -x "$DEST/extract/nic.udeb" "$DEST/extract/nic"
test -f "$DEST/extract/nic/lib/modules/6.12.107+deb13-amd64/kernel/drivers/net/ethernet/realtek/r8169.ko.xz"
mkdir -p "$DEST/overlay/lib/modules"
cp -a "$DEST/extract/nic/lib/modules/." "$DEST/overlay/lib/modules/"
# Preserve the original Debian installer layout. Add module dependency metadata.
mkdir -p "$DEST/original/lib/modules"
cp -an "$DEST/extract/nic/lib/modules/." "$DEST/original/lib/modules/"
DEPMOD=/usr/sbin/depmod
test -x "$DEPMOD"
"$DEPMOD" -b "$DEST/original" 6.12.107+deb13-amd64
for f in modules.dep modules.dep.bin modules.alias modules.alias.bin modules.symbols modules.symbols.bin; do
  src="$DEST/original/lib/modules/6.12.107+deb13-amd64/$f"
  if test -f "$src"; then
    mkdir -p "$DEST/overlay/lib/modules/6.12.107+deb13-amd64"
    cp "$src" "$DEST/overlay/lib/modules/6.12.107+deb13-amd64/$f"
  fi
done
# Embed the current PXE preseed so cdrom detection does not race URL preseed.
cp "$BASE/preseed.cfg" "$DEST/overlay/preseed.cfg"
mkdir -p "$DEST/overlay/usr/lib/debian-installer-startup.d"
cat > "$DEST/overlay/usr/lib/debian-installer-startup.d/S29veyra-media" <<'HOOK'
#!/bin/sh
# Original Debian ISO installer, not generic netboot. Called before cdrom-detect.
# Do not write to or partition any local storage.
LOG=/var/log/veyra-media.log
exec >>"$LOG" 2>&1
echo "VEYRA_MEDIA_INIT $(date)"
modprobe r8169 || echo 'VEYRA_MEDIA_R8169_LOAD_FAILED'
# Bring up first wired interface; exclude loopback.
IFACE=''
for p in /sys/class/net/*; do
  n=${p##*/}
  [ "$n" = lo ] && continue
  [ -e "$p/device" ] || continue
  IFACE=$n
  break
done
if [ -z "$IFACE" ]; then
  echo 'VEYRA_MEDIA_NO_NETWORK_IFACE'
  exit 0
fi
ip link set "$IFACE" up || true
udhcpc -i "$IFACE" -n -q -t 5 -T 5 || {
  echo 'VEYRA_MEDIA_DHCP_UNAVAILABLE'
  exit 0
}
mkdir -p /cdrom
# Memory-backed ISO, not written to the laptop hard drive.
if ! wget -q -T 45 -O /tmp/veyra-installer.iso http://10.10.110.13:8098/veyra/v0.9.2/Veyra-AutoInstall-v0.9.2.iso; then
  echo 'VEYRA_MEDIA_ISO_HTTP_FAILED'
  rm -f /tmp/veyra-installer.iso
  exit 0
fi
modprobe loop || true
if mount -t iso9660 -o ro,loop /tmp/veyra-installer.iso /cdrom; then
  test -f /cdrom/.disk/info && echo VEYRA_MEDIA_MOUNT_OK || echo VEYRA_MEDIA_MISSING_DISK_INFO
else
  echo 'VEYRA_MEDIA_LOOP_MOUNT_FAILED'
fi
exit 0
HOOK
chmod +x "$DEST/overlay/usr/lib/debian-installer-startup.d/S29veyra-media"
# Merge staged files into an extracted copy of the ORIGINAL ISO initrd.
# Never concatenate multiple gzip members; Linux initramfs parser may reject them.
cp -a "$DEST/overlay/." "$DEST/original/"
test -c "$DEST/original/dev/console" || { echo 'STOP: console device missing'; exit 65; }
test -c "$DEST/original/dev/null" || { echo 'STOP: null device missing'; exit 65; }
test -f "$DEST/original/usr/lib/debian-installer-startup.d/S29veyra-media"
(cd "$DEST/original"; find . -print0 | cpio --null --format=newc -o 2>/dev/null | gzip -9 > "$DEST/initrd.gz")
gzip -t "$DEST/initrd.gz"
mkdir -p "$DEST/reinspect"
(cd "$DEST/reinspect"; gzip -dc "$DEST/initrd.gz" | cpio -idmu --quiet)
test -c "$DEST/reinspect/dev/console"
test -c "$DEST/reinspect/dev/null"
test -f "$DEST/reinspect/usr/lib/debian-installer-startup.d/S29veyra-media"
test "$(sha256sum "$BASE/vmlinuz" | awk '{print $1}')" = 2b2358b37674d2505350528875bb17afae2a36522a9e8a9417eaca65a7da0e08
echo '=== STAGED SINGLE-ARCHIVE MEDIA INITRD ==='
sha256sum "$DEST/initrd.gz"
echo 'VEYRA_MEDIA_SINGLE_ARCHIVE_CANDIDATE_STAGED_NO_LIVE_CHANGE'
