#!/usr/bin/env bash
# Publish only UEFI fallback boot repair for Veyra N automatic installer.
set -Eeuo pipefail
[[ $(id -u) -eq 0 ]] || { echo 'Must run as root on Node C'; exit 77; }
BASE=/srv/veyra-pxe/http
NET=$BASE/veyra/v0.9.2-netboot
F=$NET/preseed-auto.cfg
SERVE=$BASE/veyra/install-logs
ORIG=$BASE/veyra/v0.9.2
test -s "$F" && test -s "$NET/initrd.gz" && test -s "$NET/vmlinuz"
test "$(sha256sum "$ORIG/vmlinuz" | cut -d' ' -f1)" = 2b2358b37674d2505350528875bb17afae2a36522a9e8a9417eaca65a7da0e08
test "$(sha256sum "$ORIG/initrd.gz" | cut -d' ' -f1)" = 8de544ab627ab794504c530c82de621814386b5b67a492f1e3133390c47ea933
BEFORE=$(sha256sum "$BASE/autoexec.ipxe" /srv/veyra-pxe/tftp/autoexec.ipxe "$NET/initrd.gz" "$NET/vmlinuz")
B=/srv/veyra-pxe/backups/veyra-uefi-repair-$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p "$B" "$SERVE"
cp -a "$F" "$B/preseed-auto.cfg"
cat >"$B/veyra-finalize.sh" <<'FINISH'
#!/bin/sh
set -eu
stage() {
 logger -t veyra-finalize "$1"
 echo "VEYRA_FINALIZE: $1"
}
stage 'BEGIN bootloader fallback repair'
test -d /sys/firmware/efi || { stage 'FATAL: installer not UEFI booted'; exit 21; }
test -d /target/usr || { stage 'FATAL: target root unavailable'; exit 22; }
# Firmware cannot read EFI Boot* NVRAM. No call may write EFI NVRAM.
test -d /target/boot/efi/EFI || { stage 'FATAL: no mounted EFI System Partition'; exit 23; }
printf 'grub-efi-amd64 grub2/update_nvram boolean false\ngrub-efi-amd64 grub2/force_efi_extra_removable boolean true\n' | in-target debconf-set-selections
stage 'Installing GRUB EFI binaries'
in-target apt-get -y install grub-efi-amd64
stage 'Writing fallback EFI/BOOT/BOOTX64.EFI without NVRAM'
in-target grub-install --target=x86_64-efi --efi-directory=/boot/efi --bootloader-id=Veyra --removable --no-nvram --recheck
test -s /target/boot/efi/EFI/BOOT/BOOTX64.EFI || { stage 'FATAL: BOOTX64.EFI not produced'; exit 24; }
in-target update-grub
test -s /target/boot/grub/grub.cfg || { stage 'FATAL: no grub.cfg'; exit 25; }
stage 'Bootloader validated; installing Veyra payload'
in-target curl -fsSL http://10.10.110.13:8098/veyra/v0.9.2/veyra-payload.tar.gz -o /root/veyra-payload.tar.gz
in-target tar -xzf /root/veyra-payload.tar.gz -C /root
in-target /bin/bash -c 'cd /root/veyra && chmod +x scripts/*.sh && ./scripts/install-debian.sh'
stage 'Refreshing GRUB configuration'
in-target update-grub
in-target rm -rf /root/veyra /root/veyra-payload.tar.gz
stage 'SUCCESS fallback EFI and Veyra installed'
FINISH
python3 - "$F" "$B/preseed-next.cfg" <<'PY'
from pathlib import Path
import sys
original,updated=map(Path,sys.argv[1:])
s=original.read_text()
assert 'partman/early_command' in s and 'veyra-disk-probe.sh' in s
assert 'preseed/early_command' in s and 'log_port' not in s
assert 'veyra-payload.tar.gz' in s and 'scripts/install-debian.sh' in s
assert 'grub-installer/update_nvram boolean false' in s
assert 'grub-installer/force-efi-extra-removable boolean true' in s
assert 'grub-installer/skip boolean true' not in s
lines=s.splitlines()
prefix='d-i preseed/late_command string '
matches=[i for i,line in enumerate(lines) if line.startswith(prefix)]
assert len(matches)==1 and 'grub-install' in lines[matches[0]]
lines[matches[0]]=prefix+'wget -q -O /tmp/veyra-finalize.sh http://10.10.110.13:8098/veyra/install-logs/veyra-finalize.sh && sh /tmp/veyra-finalize.sh'
grub=[i for i,line in enumerate(lines) if line.startswith('d-i grub-installer/only_debian')]
assert len(grub)==1
lines.insert(grub[0],'d-i grub-installer/skip boolean true')
updated.write_text('\n'.join(lines)+'\n')
PY
install -m 0644 "$B/veyra-finalize.sh" "$SERVE/veyra-finalize.sh.next"
mv -f "$SERVE/veyra-finalize.sh.next" "$SERVE/veyra-finalize.sh"
curl -fsS http://127.0.0.1:8098/veyra/install-logs/veyra-finalize.sh | grep -Fq -- '--no-nvram'
install -m 0644 "$B/preseed-next.cfg" "$F.next"
mv -f "$F.next" "$F"
curl -fsS http://127.0.0.1:8098/veyra/v0.9.2-netboot/preseed-auto.cfg | grep -Fq 'grub-installer/skip boolean true'
test "$BEFORE" = "$(sha256sum "$BASE/autoexec.ipxe" /srv/veyra-pxe/tftp/autoexec.ipxe "$NET/initrd.gz" "$NET/vmlinuz")"
echo VEYRA_UEFI_FALLBACK_FIX_PUBLISHED
echo "BACKUP=$B/preseed-auto.cfg"
echo "LOG_URL=http://10.10.110.13:8098/veyra/install-logs/latest.log"
echo "NEXT_N_BOOT_DESTRUCTIVE=YES"
