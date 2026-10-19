#!/usr/bin/env bash
# Veyra Terminal 1 guarded recovery - no provider profile or OBS changes.
# Restores documented last-known-good Cage debug launcher when installed.
set -Eeuo pipefail
[ "$(id -u)" -eq 0 ] || { echo 'Run with sudo'; exit 2; }
UNIT=veyra-kiosk.service
DROP=/etc/systemd/system/veyra-kiosk.service.d
DEBUG=/usr/local/sbin/veyra-cage-debug.sh
BACKUP=/var/backups/veyra-tty1-recovery-$(date +%Y%m%d-%H%M%S)
mkdir -p "$BACKUP" "$DROP"
systemctl cat "$UNIT" >"$BACKUP/pre-unit.txt" 2>&1 || :
cp -a "$DROP" "$BACKUP/systemd-dropins"
systemctl show "$UNIT" -p ExecStart -p ActiveState -p Result >"$BACKUP/pre-status.txt"
journalctl -b -u "$UNIT" -n 120 --no-pager >"$BACKUP/pre-journal.txt" || :
echo "Backup: $BACKUP"
echo '=== PRESERVED ==='
echo 'Chrome provider profiles, Home application, OBS :92 session, getty@tty3.'
echo '=== PRE-FLIGHT ==='
systemctl is-active seatd || :
ls -l /run/seatd.sock || :
printf 'Veyra Python module: '
cd /opt/veyra
env PYTHONPATH=/opt/veyra /opt/veyra/.venv/bin/python -c 'import veyra.kiosk;print("OK")' || {
 echo 'Python import failed. No graphical configuration changed.'
 exit 5
}
# Prevent selecting a missing debug script. Existing scripts are not replaced.
if [ ! -x "$DEBUG" ]; then
 echo "Known-good debug launcher missing ($DEBUG). Refusing unverified graphical override."
 echo "Captured preflight diagnostics in $BACKUP"
 exit 6
fi
bash -n "$DEBUG" || { echo 'Existing debug launcher has a shell syntax error'; exit 7; }
echo '=== RESTORE DOCUMENTED WORKING CAGE LAUNCHER ==='
cat >"$DROP/98-veyra-cage-recovery.conf" <<EOF
[Service]
ExecStart=
ExecStart=$DEBUG
WorkingDirectory=/opt/veyra
Environment=PYTHONPATH=/opt/veyra
Environment=LIBSEAT_BACKEND=seatd
Environment=SEATD_SOCK=/run/seatd.sock
Restart=no
EOF
# Remove only known Sway candidate override; preserve other existing overrides.
if [ -e "$DROP/99-veyra-sway-candidate.conf" ]; then
 mv "$DROP/99-veyra-sway-candidate.conf" "$BACKUP/99-veyra-sway-candidate.conf"
fi
# A historical debug.conf overrides anything beginning 98, so check effective command.
systemctl daemon-reload
EFFECTIVE=$(systemctl show "$UNIT" -p ExecStart --value)
echo "$EFFECTIVE"
case "$EFFECTIVE" in *"$DEBUG"*) ;; *)
 echo 'Another override takes precedence; restored prior configuration.'
 rm -f "$DROP/98-veyra-cage-recovery.conf"
 [ -f "$BACKUP/99-veyra-sway-candidate.conf" ] && mv "$BACKUP/99-veyra-sway-candidate.conf" "$DROP/99-veyra-sway-candidate.conf"
 systemctl daemon-reload;exit 8;;
esac
systemctl reset-failed "$UNIT"
systemctl restart "$UNIT" || :
sleep 6
STATUS=$(systemctl is-active "$UNIT" || :)
echo "Kiosk after 6s: $STATUS"
journalctl -b -u "$UNIT" -n 65 --no-pager >"$BACKUP/post-journal.txt" || :
if [ "$STATUS" != active ]; then
 echo 'GRAPHICAL_RECOVERY_NOT_VERIFIED'
 tail -n 45 "$BACKUP/post-journal.txt"
 echo 'Recovery override remains for inspection; restore by running:'
 echo "sudo cp -a $BACKUP/systemd-dropins/. $DROP/ && sudo rm -f $DROP/98-veyra-cage-recovery.conf && sudo systemctl daemon-reload"
 exit 9
fi
echo 'GRAPHICAL_SERVICE_ACTIVE — check laptop VT1 visually.'
echo 'Keep Terminal 3 as recovery. Browser responsiveness still requires human verification.'
