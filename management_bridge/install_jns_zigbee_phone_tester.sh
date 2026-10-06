#!/usr/bin/env bash
# ==============================================================================
# Install JNS Zigbee Phone Walk-Round Tester on Node C
# ==============================================================================
# PURPOSE
#   Installs the touch-friendly Zigbee walk-round testing web interface on the
#   Node C management host and starts it as a persistent systemd service.
#
#   The phone UI identifies one lamp/socket at a time, waits for the user to
#   confirm Working / Not working, records the result, and only then advances.
#
# INSTALLS
#   /usr/local/sbin/jns-zigbee-device-control.sh
#   /opt/jns-zigbee-phone-tester/server.py
#   /etc/systemd/system/jns-zigbee-phone-tester.service
#   Runtime results under /var/lib/jns-zigbee-phone-tester/
#
# WEB ADDRESS
#   http://10.10.10.236:8091/
#
# SAFETY
#   LAN-only tool. Do NOT port-forward TCP/8091 to the Internet.
#   The controller uses a fixed Zigbee lighting allow-list and ON/OFF only.
#
# DOCUMENTATION CATALOGUE DESCRIPTION
#   "Installs the phone-friendly interactive Zigbee walk-round tester on Node C.
#    The UI names one lamp/socket, waits for manual Working/Not working
#    confirmation, records results and then advances; includes ALL OFF."
# ==============================================================================

set -euo pipefail

[[ $EUID -eq 0 ]] || { echo "Run as root on Node C." >&2; exit 1; }

BASE="https://raw.githubusercontent.com/jamienewton2269/JNS-Home-Assistant-Deployment/main/management_bridge"
install -d -m 0755 /opt/jns-zigbee-phone-tester
install -d -m 0755 /var/lib/jns-zigbee-phone-tester

curl -fsSL "$BASE/jns-zigbee-device-control.sh" -o /usr/local/sbin/jns-zigbee-device-control.sh
chmod 0755 /usr/local/sbin/jns-zigbee-device-control.sh

curl -fsSL "$BASE/jns_zigbee_phone_tester.py" -o /opt/jns-zigbee-phone-tester/server.py
chmod 0755 /opt/jns-zigbee-phone-tester/server.py

cat >/etc/systemd/system/jns-zigbee-phone-tester.service <<'UNIT'
[Unit]
Description=JNS Zigbee Phone Walk-Round Tester
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 /opt/jns-zigbee-phone-tester/server.py
Restart=on-failure
RestartSec=3
User=root
Group=root
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=read-only

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable --now jns-zigbee-phone-tester.service

DOC_DIR="/home/github-runner/steward-web/docs"
if [[ -d "$DOC_DIR" ]]; then
  CAT="$DOC_DIR/script-catalogue.txt"
  touch "$CAT"
  tmp="$(mktemp)"
  grep -v -E '^(install_jns_zigbee_phone_tester\.sh|jns-zigbee-device-control\.sh|jns_zigbee_phone_tester\.py) - ' "$CAT" > "$tmp" || true
  cat >>"$tmp" <<'DOC'
install_jns_zigbee_phone_tester.sh - Installs the phone-friendly interactive Zigbee walk-round tester on Node C and starts it as a persistent systemd service on TCP/8091.
jns-zigbee-device-control.sh - Restricted Zigbee lighting helper used by the tester; sends only ON/OFF to the approved lighting allow-list and provides emergency all-off.
jns_zigbee_phone_tester.py - Phone-friendly interactive Zigbee walk-round web interface; names each device, waits for Working/Not working confirmation, records the result, then advances.
DOC
  cat "$tmp" > "$CAT"
  rm -f "$tmp"
fi

echo
echo "=== JNS ZIGBEE PHONE TESTER INSTALLED ==="
systemctl --no-pager --full status jns-zigbee-phone-tester.service | sed -n '1,12p'
echo
echo "Open on your phone while connected to the home LAN:"
echo "  http://10.10.10.236:8091/"
