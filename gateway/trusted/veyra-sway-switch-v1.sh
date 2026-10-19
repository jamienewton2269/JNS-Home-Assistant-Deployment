#!/usr/bin/env bash
# Controlled Sway candidate activation with automatic rollback after 3 minutes.
# Usage: sudo bash veyra-sway-switch.sh activate | confirm | rollback
set -Eeuo pipefail
[ "$(id -u)" = 0 ] || { echo "sudo required"; exit 2; }
act="${1:-}"
drop=/etc/systemd/system/veyra-kiosk.service.d/99-veyra-sway-candidate.conf
state=/var/lib/veyra-sway-trial
mkdir -p "$state"
case "$act" in
 activate)
  test -x /opt/veyra/scripts/veyra-sway-session.sh || { echo 'Run staging installer first'; exit 3; }
  test ! -e "$drop" || { echo 'Trial already configured; use rollback first'; exit 4; }
  systemctl is-active --quiet veyra-kiosk.service || { echo 'Existing Cage kiosk not active'; exit 5; }
  systemctl cat veyra-kiosk.service > "$state/pretrial-unit.txt"
  cat > "$drop" <<'CONF'
[Service]
ExecStart=
ExecStart=/opt/veyra/scripts/veyra-sway-session.sh
Restart=no
CONF
  systemctl daemon-reload
  # Arm rollback BEFORE switching compositor.
  systemd-run --unit=veyra-sway-auto-rollback --on-active=180s \
    /usr/bin/bash /opt/veyra/scripts/veyra-sway-switch.sh rollback
  systemctl reset-failed veyra-kiosk.service
  systemctl restart --no-block veyra-kiosk.service
  echo 'Sway trial started; screen may go blank briefly.'
  echo 'Auto rollback in 180 seconds unless confirmed.'
  echo 'If the display shows the Veyra bar and playback works, run:'
  echo 'sudo bash /opt/veyra/scripts/veyra-sway-switch.sh confirm'
 ;;
 confirm)
  test -e "$drop" || { echo 'No active Sway trial'; exit 6; }
  systemctl is-active --quiet veyra-kiosk.service || { echo 'Kiosk not active; do not confirm'; exit 7; }
  systemctl stop veyra-sway-auto-rollback.timer 2>/dev/null || :
  systemctl stop veyra-sway-auto-rollback.service 2>/dev/null || :
  touch "$state/confirmed"
  echo 'Sway trial confirmed; current kiosk service configuration retained.'
 ;;
 rollback)
  rm -f "$drop"
  systemctl daemon-reload
  systemctl reset-failed veyra-kiosk.service
  systemctl restart --no-block veyra-kiosk.service
  echo 'Restored previous Cage service overrides; kiosk restarting.'
 ;;
 *) echo 'Usage: activate | confirm | rollback'; exit 2;;
esac
