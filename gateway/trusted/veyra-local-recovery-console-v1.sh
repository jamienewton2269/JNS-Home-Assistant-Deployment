#!/usr/bin/env bash
# Veyra local recovery console v1.0 — independent physical VT login + read-only diagnostics.
set -Eeuo pipefail
[[ $(id -u) -eq 0 ]] || { echo 'Use sudo'; exit 2; }
command -v systemctl >/dev/null
id jnsadmin >/dev/null
mkdir -p /usr/local/libexec /etc/systemd/system/getty@tty3.service.d
cat >/usr/local/libexec/veyra-diagnostics <<'DIAG'
#!/usr/bin/env bash
set -u
export SYSTEMD_PAGER=cat PAGER=cat
while :; do
 clear
 echo 'VEYRA LOCAL DIAGNOSTICS (read-only)'
 echo 'F1: Console information | Ctrl+Alt+F1: Veyra display | Ctrl+C: Quit'
 echo "Updated: $(date -Is)"
 echo
 echo '=== DISPLAY COMPOSITOR ==='
 pgrep -af '(/usr/bin/cage|/usr/bin/sway|dbus-run-session)' | head -n 12 || :
 echo
 echo '=== SERVICES ==='
 for service in veyra-kiosk veyra-boot veyra-view veyra-core seatd ssh; do
  printf '%-21s' "$service"
  timeout 2 systemctl is-active "$service" 2>/dev/null || echo unavailable
 done
 echo
 echo '=== CURRENT GRAPHICAL LAUNCHER ==='
 timeout 3 systemctl show veyra-kiosk.service -p ExecStart --value 2>/dev/null | cut -c 1-180 || :
 echo
 echo '=== OBS / BROWSER ==='
 pgrep -af 'obs|Xvfb|chrome --kiosk' | head -n 12 || :
 echo
 echo '=== RESOURCES ==='
 uptime
 df -h / | tail -n 1
 free -h | head -n 2
 echo
 echo '=== LATEST KIOSK ERRORS ==='
 timeout 3 journalctl -b -u veyra-kiosk.service -p warning --no-pager -n 8 2>/dev/null | tail -n 8 || :
 echo
 echo 'Updates every 5 seconds. Ctrl+C stops dashboard; type exit to log out.'
 sleep 5
done
DIAG
chmod 755 /usr/local/libexec/veyra-diagnostics
cat >/etc/systemd/system/getty@tty3.service.d/veyra-local-console.conf <<'UNIT'
[Unit]
Description=Veyra local recovery login on VT3
[Service]
TTYVTDisallocate=yes
UNIT
cat >/etc/profile.d/veyra-console.sh <<'PROFILE'
# Diagnostics shortcut available on any local Veyra login.
veyra-status() { /usr/local/libexec/veyra-diagnostics; }
PROFILE
chmod 644 /etc/profile.d/veyra-console.sh
# Keep real password authentication and do not enable automatic root login.
systemctl daemon-reload
systemctl enable --now getty@tty3.service
echo 'VEYRA_LOCAL_CONSOLE_PASS'
echo 'Press Ctrl+Alt+F3 on the Lenovo physical keyboard.'
echo 'Log in as jnsadmin with your existing password, then run: veyra-status'
echo 'Return to graphical session using Ctrl+Alt+F1 (or Ctrl+Alt+F2 if display uses VT2).'
echo 'If the screen is completely dead, SSH still remains an independent fallback.'
