#!/usr/bin/env bash
# Restore HTTP access to the Veyra original ISO's media tree. NEVER modify PXE boot artifacts.
set -Eeuo pipefail
[[ $(id -u) -eq 0 ]] || { echo "STOP: run as root on Node C" >&2; exit 77; }
D=/srv/veyra-pxe/http/veyra/v0.9.2
ISO="$D/Veyra-AutoInstall-v0.9.2.iso"
EXPECT=53e31c84dc0613773e1224215e03004423d3daaaf5ff6cbd518dd1f17f15e246
echo "$EXPECT  $ISO" | sha256sum -c -
command -v xorriso >/dev/null
for f in /srv/veyra-pxe/http/autoexec.ipxe "$D/vmlinuz" "$D/initrd.gz"; do test -s "$f"; done
BEFORE="$(sha256sum /srv/veyra-pxe/http/autoexec.ipxe "$D/vmlinuz" "$D/initrd.gz")"
BACKUP=/srv/veyra-pxe/backups/veyra-http-media-$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p "$BACKUP"
printf '%s\n' "$BEFORE" > "$BACKUP/boot.sha256"
# Source integrity: a real release file inside the original ISO.
xorriso -indev "$ISO" -ls /dists/trixie/Release >/dev/null 2>&1
xorriso -indev "$ISO" -ls /.disk/info >/dev/null 2>&1
for dir in .disk dists pool; do
  echo "=== Publishing media directory $dir ==="
  if [[ -e "$D/$dir" && ! -d "$D/$dir" ]]; then
    echo "STOP: unexpected existing non-directory $D/$dir" >&2; exit 65
  fi
  # Stage each directory, then rename only if destination is absent.
  if [[ ! -e "$D/$dir" ]]; then
    STAGE="$D/.veyra-media-$dir-$$"
    trap 'rm -rf "$STAGE"' EXIT
    xorriso -osirrox on -indev "$ISO" -extract "/$dir" "$STAGE" >/dev/null
    test -d "$STAGE"
    if [[ "$dir" == dists ]]; then test -s "$STAGE/trixie/Release"; fi
    if [[ "$dir" == .disk ]]; then test -s "$STAGE/info"; fi
    if [[ "$dir" == pool ]]; then find "$STAGE" -type f -print -quit | grep -q .; fi
    mv -n "$STAGE" "$D/$dir"
    trap - EXIT
  else
    echo "Existing $dir preserved; checking files"
  fi
done
test -s "$D/.disk/info"
test -s "$D/dists/trixie/Release"
find "$D/pool" -type f -print -quit | grep -q .
AFTER="$(sha256sum /srv/veyra-pxe/http/autoexec.ipxe "$D/vmlinuz" "$D/initrd.gz")"
[[ "$BEFORE" == "$AFTER" ]] || { echo 'STOP: unexpected PXE artifact changes!' >&2; exit 80; }
for f in .disk/info dists/trixie/Release; do
  code=$(curl --silent --output /dev/null --write-out '%{http_code}' "http://127.0.0.1:8098/veyra/v0.9.2/$f")
  [[ "$code" == 200 ]] || { echo "STOP: HTTP $code for $f" >&2; exit 81; }
done
echo "VEYRA_MEDIA_TREE_HTTP_READY"
echo "VEYRA_PXE_BOOT_ARTIFACTS_UNCHANGED"
echo "backup=$BACKUP"
