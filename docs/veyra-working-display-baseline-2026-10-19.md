# Veyra graphical recovery baseline — 2026-10-19

**Confirmed on Lenovo:** Debian boots; user confirmed Veyra is visible, with working mouse and keyboard. `/var/log/veyra-install.log` reported `INSTALL_PASS Veyra v0.9.1` although PXE deployment path is v0.9.2.

## Proven root cause and fix
Kiosk diagnostic showed `ModuleNotFoundError: No module named 'veyra'`. The successful systemd service override is:
```ini
[Service]
WorkingDirectory=/opt/veyra
Environment=PYTHONPATH=/opt/veyra
Restart=no
```
After this, `import veyra.kiosk` returned `VEYRA_IMPORT_PASS`; `veyra-kiosk.service` was active/running; graphical Veyra was visible and interactive. **Capture exact service overrides and deployed runtime before changing them.** The current PXE payload is not yet proven to include this fix.

## Additional conditions during successful launch
- Debian Trixie, Cage Wayland compositor, Intel DRM devices.
- `seatd` installed and active, `seatd -g video`, `/run/seatd.sock` root:video; veyra user in group video.
- `seatd.conf`: `LIBSEAT_BACKEND=seatd`, `SEATD_SOCK=/run/seatd.sock`.
- `debug.conf` changed `ExecStart` to `/usr/local/sbin/veyra-cage-debug.sh` for diagnostics. Retain exact working state in backup; do not blindly ship debug wrapper in production.
- `safety.conf` set `Restart=no`. Previous `Restart=always` produced 6550 abandoned seat0/tty1 sessions, overwhelming logind; a reboot cleared these. Use bounded restarts in final system.
- UEFI fallback GRUB workaround `grub-install --target=x86_64-efi --efi-directory=/boot/efi --bootloader-id=Veyra --removable --no-nvram --recheck`; Chrome shared libraries installed in preseed before original installer.
- Kiosk boot persistence across reboot **not yet proven**; do not assume working automatic startup.

## PXE and later requests
- Node C paths `/srv/veyra-pxe/http`, `/srv/veyra-pxe/tftp`, current preseed `/srv/veyra-pxe/http/veyra/v0.9.2-netboot/preseed-auto.cfg`, payload `/srv/veyra-pxe/http/veyra/v0.9.2/veyra-payload.tar.gz`.
- Menu currently labels N as diagnostic although it is destructive automated installation; old V path broken. Correct only after installer validation.
- Viewer name Veyra; planned programme title autocomplete/provider URL discovery, keyboard default UK with in-app choice, and display-language selection. These are **not yet deployed**.

## Safety and secrets
Preseed contains a hashed jnsadmin password; `/etc/veyra` may contain tokens and login profiles. Never commit raw recovery archives to GitHub. Capture actual Node C and Lenovo files in a private encrypted archive before redeployment.
