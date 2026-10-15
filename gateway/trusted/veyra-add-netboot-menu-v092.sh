#!/usr/bin/env bash
# Menu-only change: no boot binaries, ISO, DHCP, or service restart.
set -Eeuo pipefail
[[ $(id -u) -eq 0 ]] || { echo 'Run on Node C as root'; exit 77; }
HTTP=/srv/veyra-pxe/http
MENU=$HTTP/autoexec.ipxe
TFTP=/srv/veyra-pxe/tftp/autoexec.ipxe
NET=$HTTP/veyra/v0.9.2-netboot
[[ -f "$MENU" && -f "$TFTP" ]] || { echo 'STOP: missing existing menu'; exit 64; }
for f in vmlinuz initrd.gz preseed.cfg boot.ipxe; do test -s "$NET/$f"; done
grep -Fq 'item --key v veyra092' "$MENU"
grep -Fq 'item --key s shell' "$MENU"
grep -Fq 'choose --default shell --timeout 10000 target' "$MENU"
grep -Fq ':veyra092' "$MENU"
! grep -Fq 'item --key n veyra-netboot' "$MENU" || { echo 'Already installed'; exit 0; }
BACKUP=/srv/veyra-pxe/backups/menu-netboot-$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p "$BACKUP"
cp -a "$MENU" "$BACKUP/autoexec.ipxe"
cp -a "$TFTP" "$BACKUP/autoexec-tftp.ipxe"
python3 - "$MENU" "$BACKUP/new.ipxe" <<'PY'
from pathlib import Path
import sys
source=Path(sys.argv[1]).read_text()
assert source.count("item --key s shell")==1
assert source.count(":veyra092")==1
source=source.replace("item --key s shell", "item --key n veyra-netboot Debian Network Installer (diagnostic, no automatic disk changes)\nitem --key s shell",1)
source=source.replace(":veyra092", ":veyra-netboot\necho Launching independent Debian network installer\nchain http://10.10.110.13:8098/veyra/v0.9.2-netboot/boot.ipxe || goto bootfail\n:veyra092",1)
Path(sys.argv[2]).write_text(source)
PY
grep -Fq 'choose --default shell --timeout 10000 target' "$BACKUP/new.ipxe"
grep -Fq 'item --key n veyra-netboot' "$BACKUP/new.ipxe"
grep -Fq 'chain http://10.10.110.13:8098/veyra/v0.9.2-netboot/boot.ipxe' "$BACKUP/new.ipxe"
grep -Fq 'kernel ${base}/vmlinuz initrd=initrd.magic' "$BACKUP/new.ipxe"
install -m 0644 "$BACKUP/new.ipxe" "$MENU.new"
mv -f "$MENU.new" "$MENU"
cp -a "$MENU" "$TFTP"
cmp "$MENU" "$TFTP"
for f in vmlinuz initrd.gz; do sha256sum "$NET/$f"; done
echo "VEYRA_MENU_ONLY_NETBOOT_OPTION_PUBLISHED"
echo "ROLLBACK_DIR=$BACKUP"
