#!/usr/bin/env bash
# Install staged Veyra-owned compositor candidate; does NOT change active Cage session.
set -Eeuo pipefail
[ "$(id -u)" = 0 ] || { echo 'Run via sudo'; exit 2; }
test -s /opt/veyra/veyra/kiosk.py
test -s /opt/veyra/scripts/veyra-session.sh
if ! grep -q '_start_home_server' /opt/veyra/veyra/kiosk.py; then
 echo 'Veyra Home API patch required before compositor candidate'; exit 3
fi
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends sway waybar curl
mkdir -p /etc/veyra /opt/veyra/scripts
cat >/opt/veyra/scripts/veyra-nav <<'NAV'
#!/bin/bash
set -euo pipefail
case "${1:-home}" in
 home|back)
  # Compositor-owned navigation fallback. Detailed cross-provider backstack comes later.
  code=$(curl -sS --max-time 5 -o /dev/null -w '%{http_code}' -X POST http://127.0.0.1:8767/home)
  [ "$code" = 204 ];;
 *) exit 2;;
esac
NAV
chmod 755 /opt/veyra/scripts/veyra-nav
cat >/etc/veyra/sway.conf <<'SWAY'
# Veyra owns navigation keys above Chrome.
font pango:Sans 11
output * bg #10151e solid_color
xwayland disable
focus_follows_mouse no
bindsym --no-repeat Escape exec /opt/veyra/scripts/veyra-nav back
bindsym --no-repeat Home exec /opt/veyra/scripts/veyra-nav home
bindsym --no-repeat Ctrl+Shift+h exec /opt/veyra/scripts/veyra-nav home
exec /opt/veyra/.venv/bin/python -m veyra.kiosk
exec waybar --config /etc/veyra/waybar.json --style /etc/veyra/waybar.css
SWAY
cat >/etc/veyra/waybar.json <<'BAR'
{
 "layer":"overlay","position":"top","height":36,"exclusive":false,
 "modules-left":["custom/back","custom/home"],
 "modules-right":["custom/title"],
 "custom/back":{"format":"❮ BACK","on-click":"/opt/veyra/scripts/veyra-nav back","tooltip":false},
 "custom/home":{"format":"⌂ VEYRA HOME","on-click":"/opt/veyra/scripts/veyra-nav home","tooltip":false},
 "custom/title":{"format":"VEYRA • LOCAL","tooltip":false}
}
BAR
cat >/etc/veyra/waybar.css <<'CSS'
* { font-family:sans-serif; font-size:15px; }
window#waybar { background:rgba(13,18,26,.94);color:#f0f4ff; }
#custom-back,#custom-home { padding:4px 20px;background:#27384b;margin:2px 6px;border-radius:7px; }
CSS
cat >/opt/veyra/scripts/veyra-sway-session.sh <<'SESSION'
#!/usr/bin/env bash
set -euo pipefail
exec /usr/bin/dbus-run-session -- /usr/bin/sway --config /etc/veyra/sway.conf
SESSION
chmod 755 /opt/veyra/scripts/veyra-sway-session.sh
python3 -m json.tool /etc/veyra/waybar.json >/dev/null
echo 'VEYRA_COMPOSITOR_STAGED_PASS'
echo 'Existing Cage service not changed or restarted.'
echo 'ESC currently returns Home, not a full multi-page navigation history.'
echo 'Activation must be timed with rollback and graphics validation.'
