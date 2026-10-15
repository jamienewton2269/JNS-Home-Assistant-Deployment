#!/usr/bin/env bash
# Stage/publish an independent official Debian network installer candidate.
# Deliberately NEVER alter the working Veyra menu, kernel or initrd.
set -Eeuo pipefail
[[ $(id -u) -eq 0 ]] || { echo "Run as root on Node C (the existing PXE tree is root-owned)" >&2; exit 77; }
BASE=/srv/veyra-pxe/http
ORIG=$BASE/veyra/v0.9.2
FINAL=$BASE/veyra/v0.9.2-netboot
PREFIX=https://deb.debian.org/debian/dists/trixie/main/installer-amd64/current/images/netboot/debian-installer/amd64
test -f "$ORIG/preseed.cfg"
test -f "$BASE/autoexec.ipxe"
BEFORE=$(sha256sum "$BASE/autoexec.ipxe" "$ORIG/vmlinuz" "$ORIG/initrd.gz")
TMP=$(mktemp -d "$BASE/veyra/.veyra-netboot-stage.XXXXXXXX")
trap 'rm -rf "$TMP"' EXIT
echo 'Fetching official Debian Trixie netboot kernel and matching initrd...'
curl -fLsS --retry 2 --max-time 180 "$PREFIX/linux" -o "$TMP/vmlinuz"
curl -fLsS --retry 2 --max-time 180 "$PREFIX/initrd.gz" -o "$TMP/initrd.gz"
gzip -t "$TMP/initrd.gz"
file "$TMP/vmlinuz" "$TMP/initrd.gz"
# No kernel/initrd mixing: both from same official netboot directory.
cp "$ORIG/preseed.cfg" "$TMP/preseed.cfg"
# Debian's standard mirror supplies installation packages. Veyra payload
# continues to come from the existing Node C HTTP service.
grep -Fq 'deb.debian.org' "$TMP/preseed.cfg"
grep -Fq 'veyra-payload.tar.gz' "$TMP/preseed.cfg"
grep -Fq 'WDCWD10SPZX-24Z10T0' "$TMP/preseed.cfg"
# Conservative diagnostic boot path; NO automatic destructive preseed.
cat > "$TMP/boot.ipxe" <<'EOF'
#!ipxe
set base http://10.10.110.13:8098/veyra/v0.9.2-netboot
imgfree
kernel ${base}/vmlinuz initrd=initrd.gz priority=low netcfg/choose_interface=auto --- || goto failed
initrd --name initrd.gz ${base}/initrd.gz || goto failed
boot || goto failed
:failed
echo Network installer handoff failed - original Veyra boot untouched
shell
EOF
test "$(sha256sum "$BASE/autoexec.ipxe" "$ORIG/vmlinuz" "$ORIG/initrd.gz")" = "$BEFORE"
if [[ -e "$FINAL" ]]; then
 echo "Refusing to overwrite existing candidate $FINAL" >&2; exit 75
fi
chmod 0644 "$TMP"/*
chmod 0755 "$TMP"
mv "$TMP" "$FINAL"
trap - EXIT
for part in vmlinuz initrd.gz preseed.cfg boot.ipxe; do
  curl -fsS -o /dev/null "http://127.0.0.1:8098/veyra/v0.9.2-netboot/$part"
done
test "$(sha256sum "$BASE/autoexec.ipxe" "$ORIG/vmlinuz" "$ORIG/initrd.gz")" = "$BEFORE"
echo 'VEYRA_NETBOOT_CANDIDATE_PUBLISHED_WITHOUT_LIVE_BOOT_CHANGES'
sha256sum "$FINAL/vmlinuz" "$FINAL/initrd.gz"
echo 'To test independently in iPXE shell: chain http://10.10.110.13:8098/veyra/v0.9.2-netboot/boot.ipxe'
