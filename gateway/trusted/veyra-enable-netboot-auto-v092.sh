#!/usr/bin/env bash
# Enable unattended Veyra v0.9.2 ONLY when N is explicitly selected.
# Never touch the proven Debian/Realtek kernel or initrd, V entry or PXE services.
set -Eeuo pipefail
[[ $(id -u) -eq 0 ]] || { echo 'STOP: run as root on Node C'; exit 77; }
HTTP=/srv/veyra-pxe/http
D="$HTTP/veyra/v0.9.2-netboot"
ORIG="$HTTP/veyra/v0.9.2"
MENU="$HTTP/autoexec.ipxe"
TFTP=/srv/veyra-pxe/tftp/autoexec.ipxe
HOST=10.10.110.13
[[ -f "$D/initrd.gz" && -f "$D/vmlinuz" && -f "$ORIG/preseed.cfg" && -f "$MENU" && -f "$TFTP" ]]
grep -Fq 'item --key n veyra-netboot' "$MENU"
grep -Fq 'choose --default shell --timeout 10000 target' "$MENU"
grep -Fq ':veyra-netboot' "$MENU"
grep -Fq ':veyra092' "$MENU"
[[ "$(sha256sum "$ORIG/vmlinuz" | cut -d' ' -f1)" == 2b2358b37674d2505350528875bb17afae2a36522a9e8a9417eaca65a7da0e08 ]]
[[ "$(sha256sum "$ORIG/initrd.gz" | cut -d' ' -f1)" == 8de544ab627ab794504c530c82de621814386b5b67a492f1e3133390c47ea933 ]]
for f in initrd.gz vmlinuz; do curl -fsS -o /dev/null "http://127.0.0.1:8098/veyra/v0.9.2-netboot/$f"; done
curl -fsS -o /dev/null "http://127.0.0.1:8098/veyra/v0.9.2/veyra-payload.tar.gz"
KERNEL_BEFORE="$(sha256sum "$D/vmlinuz" "$D/initrd.gz" "$ORIG/vmlinuz" "$ORIG/initrd.gz")"
BACK=/srv/veyra-pxe/backups/veyra-netboot-auto-$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p "$BACK"
cp -a "$MENU" "$BACK/autoexec.ipxe"
cp -a "$TFTP" "$BACK/autoexec-tftp.ipxe"
[[ -e "$D/preseed-auto.cfg" ]] && cp -a "$D/preseed-auto.cfg" "$BACK/preseed-auto.cfg" || true
python3 - "$ORIG/preseed.cfg" "$MENU" "$BACK/preseed-auto.cfg" "$BACK/autoexec.new" <<'PY'
from pathlib import Path
import sys
seed,menufile,outseed,outmenu=map(Path,sys.argv[1:])
s=seed.read_text()
assert 'WDCWD10SPZX-24Z10T0' in s, "STOP: Lenovo target-disk guard absent"
assert 'partman/early_command' in s and 'target' in s, "STOP: disk validation missing"
assert 'veyra-payload.tar.gz' in s and 'scripts/install-debian.sh' in s, "STOP: Veyra payload stage missing"
assert 'grub-install' in s and 'update-grub' in s, "STOP: EFI bootloader stage missing"
# Disable any chance of unattended install unless the N menu option is deliberately selected.
# Standard Debian d-i native preseed support: fetch after netcfg, then partition and install.
settings={
 'd-i debian-installer/locale string':'en_GB.UTF-8',
 'd-i keyboard-configuration/xkb-keymap select':'gb',
 'd-i netcfg/choose_interface select':'auto',
 'd-i netcfg/get_hostname string':'veyra',
 'd-i netcfg/get_domain string':'home.arpa',
 'd-i mirror/country string':'manual',
 'd-i mirror/http/hostname string':'deb.debian.org',
 'd-i mirror/http/directory string':'/debian',
 'd-i mirror/http/proxy string':'',
 'd-i apt-setup/non-free-firmware boolean':'true',
 'd-i clock-setup/utc boolean':'true',
 'd-i time/zone string':'Europe/London',
 'd-i popularity-contest/participate boolean':'false',
 'd-i finish-install/reboot_in_progress note':'',
}
lines=s.splitlines()
for key,value in settings.items():
    prefix=key.rsplit(' ',1)[0]+' '
    lines=[ln for ln in lines if not ln.startswith(prefix)]
    lines.insert(0,f'{key} {value}'.rstrip())
outseed.write_text('\n'.join(lines)+'\n')
m=menufile.read_text()
start=m.index(':veyra-netboot\n')
end=m.index(':veyra092\n', start)
old=m[start:end]
assert ('priority=low' in old or 'priority=critical' in old), "STOP: unexpected N menu content"
# Preserve the original V entry byte-for-byte, including ISO kernel command.
assert 'kernel ${base}/vmlinuz initrd=initrd.magic' in m[end:]
new=''' :veyra-netboot
echo Starting unattended Veyra v0.9.2 install - THIS ERASES THE LENOVO TARGET DISK
set netbase http://10.10.110.13:8098/veyra/v0.9.2-netboot
dhcp || goto netfail
imgfree autoexec.ipxe ||
kernel ${netbase}/vmlinuz initrd=initrd.gz auto=true priority=critical netcfg/choose_interface=auto url=${netbase}/preseed-auto.cfg --- || goto bootfail
initrd --name initrd.gz ${netbase}/initrd.gz || goto bootfail
imgstat
boot || goto bootfail
'''.lstrip()
outmenu.write_text(m[:start]+new+m[end:])
assert outmenu.read_text().split(':veyra092\n',1)[1]==m.split(':veyra092\n',1)[1]
assert 'choose --default shell --timeout 10000 target' in outmenu.read_text()
PY
grep -Fq 'd-i preseed/late_command string' "$BACK/preseed-auto.cfg"
grep -Fq 'partman/early_command' "$BACK/preseed-auto.cfg"
grep -Fq 'kernel ${netbase}/vmlinuz initrd=initrd.gz auto=true priority=critical' "$BACK/autoexec.new"
[[ "$KERNEL_BEFORE" == "$(sha256sum "$D/vmlinuz" "$D/initrd.gz" "$ORIG/vmlinuz" "$ORIG/initrd.gz")" ]]
install -m 0644 "$BACK/preseed-auto.cfg" "$D/preseed-auto.cfg.next"
mv -f "$D/preseed-auto.cfg.next" "$D/preseed-auto.cfg"
curl -fsS "http://127.0.0.1:8098/veyra/v0.9.2-netboot/preseed-auto.cfg" | grep -Fq 'veyra-payload.tar.gz'
install -m 0644 "$BACK/autoexec.new" "$MENU.next"
mv -f "$MENU.next" "$MENU"
cp -a "$MENU" "$TFTP"
cmp "$MENU" "$TFTP"
if [[ "$KERNEL_BEFORE" != "$(sha256sum "$D/vmlinuz" "$D/initrd.gz" "$ORIG/vmlinuz" "$ORIG/initrd.gz")" ]]; then
  cp -a "$BACK/autoexec.ipxe" "$MENU"
  cp -a "$BACK/autoexec-tftp.ipxe" "$TFTP"
  echo 'STOP: protected installer images changed; menu rolled back' >&2
  exit 1
fi
curl -fsS "http://127.0.0.1:8098/autoexec.ipxe" | grep -Fq 'preseed-auto.cfg'
echo 'VEYRA_NETBOOT_AUTO_CONFIG_PUBLISHED'
echo 'N_OPTION_DESTRUCTIVE_INSTALL_ONLY_AFTER_EXPLICIT_SELECTION'
echo 'PXE_BOOT_BINARIES_AND_BOTH_INSTALLER_IMAGES_UNCHANGED'
echo "ROLLBACK=$BACK"
