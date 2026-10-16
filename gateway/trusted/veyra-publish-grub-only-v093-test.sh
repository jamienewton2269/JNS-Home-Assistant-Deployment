#!/usr/bin/env bash
# Publish Veyra N test candidate: Debian GRUB only, no UEFI NVRAM updates.
set -Eeuo pipefail
[[ "$(id -u)" -eq 0 ]] || { echo 'ERROR: run as root on Node C'; exit 77; }
base=/srv/veyra-pxe/http
net=$base/veyra/v0.9.2-netboot
f=$net/preseed-auto.cfg
orig=$base/veyra/v0.9.2
menu=$base/autoexec.ipxe
tftp=/srv/veyra-pxe/tftp/autoexec.ipxe
for p in "$f" "$net/vmlinuz" "$net/initrd.gz" "$menu" "$tftp" "$orig/vmlinuz" "$orig/initrd.gz"; do test -s "$p"; done
test "$(sha256sum "$orig/vmlinuz" | awk '{print $1}')" = 2b2358b37674d2505350528875bb17afae2a36522a9e8a9417eaca65a7da0e08
test "$(sha256sum "$orig/initrd.gz" | awk '{print $1}')" = 8de544ab627ab794504c530c82de621814386b5b67a492f1e3133390c47ea933
test "$(sha256sum "$net/initrd.gz" | awk '{print $1}')" = 1eb460ab49c2ccb64b004d46eab2adb1879cbc3362b45f6a3de80392f97cf904
before="$(sha256sum "$menu" "$tftp" "$net/vmlinuz" "$net/initrd.gz" "$orig/vmlinuz" "$orig/initrd.gz")"
b=/srv/veyra-pxe/backups/veyra-grub-only-$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p "$b"
cp -a "$f" "$b/preseed-auto.cfg"
python3 - "$f" "$b/proposed.cfg" <<'PY'
from pathlib import Path
import sys
src,dst=map(Path,sys.argv[1:])
s=src.read_text()
lines=s.splitlines()
def count(fragment): return sum(fragment in x for x in lines)
assert count('d-i grub-installer/skip boolean true')<=1
assert count('d-i grub-installer/only_debian boolean true')==1
assert count('d-i grub-installer/update_nvram boolean false')<=1
assert count('d-i preseed/late_command string')==1
assert count('veyra-finalize.sh')<=1
assert count('partman/early_command')==1 and 'veyra-disk-probe.sh' in s
assert count('preseed/early_command')==1
lines=[x for x in lines if x.strip() not in ('d-i grub-installer/skip boolean true','d-i grub-installer/update_nvram boolean false')]
# Debian grub-installer 1.212 reads update-nvram (hyphen), not update_nvram (underscore).
lines=[x for x in lines if not x.startswith('d-i grub-installer/update-nvram')]
lines.append('d-i grub-installer/update-nvram boolean false')
ix=next(i for i,x in enumerate(lines) if x.startswith('d-i grub-installer/only_debian'))
# Debian GRUB postinst looks for grub2/update_nvram (not grub-installer/update_nvram).
# Extra-removable installs EFI/BOOT/BOOTX64.EFI, allowing boot without Boot#### variables.
lines[ix:ix]=[
 'grub-efi-amd64 grub2/update_nvram boolean false',
 'grub-efi-amd64 grub2/force_efi_extra_removable boolean true',
 'grub-efi-amd64 grub2/force_efi_extra_removable seen true',
]
# Repair fallback UEFI boot before the app installer: an app-stage failure must not skip GRUB.
# Prior custom finalize script must not call apt to reinstall grub or potentially
# prompt for firmware variables. Keep Veyra payload action; GRUB stage now owns EFI.
i=next(i for i,x in enumerate(lines) if x.startswith('d-i preseed/late_command string'))
lines[i]='d-i preseed/late_command string in-target /usr/sbin/grub-install --target=x86_64-efi --efi-directory=/boot/efi --bootloader-id=Veyra --removable --no-nvram --recheck && in-target /usr/sbin/update-grub && in-target /usr/bin/curl -fsSL http://10.10.110.13:8098/veyra/v0.9.2/veyra-payload.tar.gz -o /root/veyra-payload.tar.gz && in-target /bin/tar -xzf /root/veyra-payload.tar.gz -C /root && in-target /bin/bash -c "cd /root/veyra && chmod +x scripts/*.sh && ./scripts/install-debian.sh" && in-target update-grub && in-target /bin/rm -rf /root/veyra /root/veyra-payload.tar.gz'
out='\n'.join(lines)+'\n'
assert 'grub-installer/skip boolean true' not in out
assert 'd-i grub-installer/update-nvram boolean false' in out
assert 'd-i grub-installer/update_nvram' not in out
assert out.count('grub2/update_nvram boolean false')==1
assert out.count('grub2/force_efi_extra_removable boolean true')==1
assert 'systemd-boot-installer' not in out
assert out.count('in-target /usr/sbin/grub-install --target=x86_64-efi --efi-directory=/boot/efi --bootloader-id=Veyra --removable --no-nvram --recheck')==1
assert out.index('in-target /usr/sbin/grub-install') < out.index('in-target /usr/bin/curl')
dst.write_text(out)
PY
# Publish atomically; other paths and the working menu remain untouched.
install -m 0644 "$b/proposed.cfg" "$f.next"
mv -f "$f.next" "$f"
curl --fail --silent --show-error http://127.0.0.1:8098/veyra/v0.9.2-netboot/preseed-auto.cfg | grep -Fq 'grub2/update_nvram boolean false'
test "$before" = "$(sha256sum "$menu" "$tftp" "$net/vmlinuz" "$net/initrd.gz" "$orig/vmlinuz" "$orig/initrd.gz")"
echo 'VEYRA_GRUB_ONLY_TEST_PUBLISHED'
echo "BACKUP=$b/preseed-auto.cfg"
echo 'N_BOOT_WILL_ERASE_TARGET_DISK=YES'
echo 'REMOTE_LOG=http://10.10.110.13:8098/veyra/install-logs/latest.log'
