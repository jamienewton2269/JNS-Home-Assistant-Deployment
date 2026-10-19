#!/usr/bin/env bash
# Veyra temporary Sway navigation trial; automatic rollback to original kiosk overrides.
set -Eeuo pipefail
[[ $(id -u) -eq 0 ]] || { echo "sudo required"; exit 2; }
ACTION="${1:-}"
D=/etc/systemd/system/veyra-kiosk.service.d
S=/var/lib/veyra-navigation-trial
mkdir -p "$S"
case "$ACTION" in
 activate)
   test -x /opt/veyra/scripts/veyra-sway-session.sh || { echo "Sway launcher missing"; exit 4; }
   test -s /etc/veyra/sway.conf || { echo "Sway config missing"; exit 4; }
   test -s /etc/veyra/waybar.json || { echo "Waybar config missing"; exit 4; }
   command -v sway >/dev/null; command -v waybar >/dev/null
   systemctl is-active --quiet veyra-kiosk.service || { echo "Cage isn't active; refusing switch"; exit 5; }
   [ ! -f "$S/armed" ] || { echo "Trial already armed"; exit 6; }
   cp -a "$D" "$S/dropins-before"
   cat >"$D/99-veyra-sway-candidate.conf" <<'UNIT'
[Service]
ExecStart=
ExecStart=/opt/veyra/scripts/veyra-sway-session.sh
Restart=no
UNIT
   cat >"$S/rollback.sh" <<'RB'
#!/usr/bin/env bash
set -e
D=/etc/systemd/system/veyra-kiosk.service.d
S=/var/lib/veyra-navigation-trial
rm -f "$D/99-veyra-sway-candidate.conf"
systemctl daemon-reload
systemctl reset-failed veyra-kiosk.service
systemctl restart --no-block veyra-kiosk.service
rm -f "$S/armed"
echo "Cage restored"
RB
   chmod 700 "$S/rollback.sh"
   touch "$S/armed"
   systemctl daemon-reload
   eff=$(systemctl show veyra-kiosk.service -p ExecStart --value)
   [[ "$eff" == *"/opt/veyra/scripts/veyra-sway-session.sh"* ]] || { "$S/rollback.sh"; echo "Sway override not selected"; exit 7; }
   systemd-run --unit=veyra-nav-trial-rollback --on-active=120s /usr/bin/bash "$S/rollback.sh" || { "$S/rollback.sh"; exit 8; }
   systemctl reset-failed veyra-kiosk.service
   systemctl restart --no-block veyra-kiosk.service
   echo "Sway trial running; automatic Cage rollback in 120 seconds."
   echo "If toolbar works, run sudo bash $0 confirm before 120 seconds."
 ;;
 confirm)
   [ -f "$S/armed" ] || { echo "No pending trial"; exit 2; }
   systemctl is-active --quiet veyra-kiosk.service || { echo "Kiosk inactive; do not confirm"; exit 9; }
   systemctl stop veyra-nav-trial-rollback.timer 2>/dev/null || :
   rm -f "$S/armed"
   echo "Sway trial retained. Visual confirmation required."
 ;;
 rollback)
   [ -f "$S/rollback.sh" ] && bash "$S/rollback.sh" || { rm -f "$D/99-veyra-sway-candidate.conf"; systemctl daemon-reload; systemctl restart --no-block veyra-kiosk.service; }
 ;;
 *) echo "Usage: sudo bash $0 activate|confirm|rollback"; exit 2 ;;
esac