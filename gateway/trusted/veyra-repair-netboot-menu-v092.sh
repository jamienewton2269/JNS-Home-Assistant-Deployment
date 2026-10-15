#!/usr/bin/env bash
# Replace only the broken N option's nested chain; preserve V and original PXE.
set -Eeuo pipefail
[[ "$(id -u)" -eq 0 ]] || { echo 'STOP: root required'; exit 77; }
H=/srv/veyra-pxe/http/autoexec.ipxe
T=/srv/veyra-pxe/tftp/autoexec.ipxe
D=/srv/veyra-pxe/http/veyra/v0.9.2-netboot
test -s "$H" && test -s "$T"
for f in vmlinuz initrd.gz boot.ipxe; do test -s "$D/$f"; done
test "$(sha256sum /srv/veyra-pxe/http/veyra/v0.9.2/vmlinuz | cut -d' ' -f1)" = 2b2358b37674d2505350528875bb17afae2a36522a9e8a9417eaca65a7da0e08
test "$(sha256sum /srv/veyra-pxe/http/veyra/v0.9.2/initrd.gz | cut -d' ' -f1)" = 8de544ab627ab794504c530c82de621814386b5b67a492f1e3133390c47ea933
B=/srv/veyra-pxe/backups/veyra-menu-handoff-$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p "$B"
cp -a "$H" "$B/autoexec.ipxe"
cp -a "$T" "$B/autoexec-tftp.ipxe"
python3 - "$H" "$B/fixed.ipxe" <<'PY'
from pathlib import Path
import sys
s=Path(sys.argv[1]).read_text()
old='chain http://10.10.110.13:8098/veyra/v0.9.2-netboot/boot.ipxe || goto bootfail'
assert s.count(old)==1
assert s.count(':veyra-netboot')==1
assert s.count(':veyra092')==1
assert 'choose --default shell --timeout 10000 target' in s
new='''set netbase http://10.10.110.13:8098/veyra/v0.9.2-netboot
echo Fetching official Debian netboot kernel and initrd directly...
dhcp || goto netfail
imgfree autoexec.ipxe ||
kernel ${netbase}/vmlinuz initrd=initrd.gz priority=low netcfg/choose_interface=auto --- || goto bootfail
initrd --name initrd.gz ${netbase}/initrd.gz || goto bootfail
imgstat
boot || goto bootfail'''
fixed=s.replace(old,new,1)
assert fixed.split(':veyra092',1)[1]==s.split(':veyra092',1)[1]
Path(sys.argv[2]).write_text(fixed)
PY
test -s "$B/fixed.ipxe"
install -m 0644 "$B/fixed.ipxe" "$H.next"
mv -f "$H.next" "$H"
cp -a "$H" "$T"
cmp "$H" "$T"
for f in autoexec.ipxe veyra/v0.9.2-netboot/vmlinuz veyra/v0.9.2-netboot/initrd.gz; do
  curl -fsS -o /dev/null "http://127.0.0.1:8098/$f"
done
echo "VEYRA_NETBOOT_N_DIRECT_HANDOFF_PUBLISHED"
echo "ROLLBACK=$B"
