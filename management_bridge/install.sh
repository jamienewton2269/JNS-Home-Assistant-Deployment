#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/jns-management-bridge"
ETC_DIR="/etc/jns-management-bridge"
SERVICE="/etc/systemd/system/jns-management-bridge.service"
REF="${JNS_BRIDGE_REF:-main}"
BASE="https://raw.githubusercontent.com/jamienewton2269/JNS-Home-Assistant-Deployment/${REF}/management_bridge"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root." >&2
  exit 1
fi

command -v python3 >/dev/null || { apt-get update && apt-get install -y python3; }
command -v ssh >/dev/null || { apt-get update && apt-get install -y openssh-client; }
command -v curl >/dev/null || { apt-get update && apt-get install -y curl; }
command -v openssl >/dev/null || { apt-get update && apt-get install -y openssl; }

install -d -m 0755 "$APP_DIR"
install -d -m 0700 "$ETC_DIR"

curl -fsSL "$BASE/server.py" -o "$APP_DIR/server.py"
chmod 0755 "$APP_DIR/server.py"

if [[ ! -f "$ETC_DIR/config.json" ]]; then
  curl -fsSL "$BASE/config.example.json" -o "$ETC_DIR/config.json"
  chmod 0600 "$ETC_DIR/config.json"
  echo "Created $ETC_DIR/config.json — edit targets before relying on SSH mode."
fi

if [[ ! -s "$ETC_DIR/token" ]]; then
  umask 077
  openssl rand -hex 32 > "$ETC_DIR/token"
fi
chmod 0600 "$ETC_DIR/token"

cat > "$SERVICE" <<'EOF'
[Unit]
Description=JNS Management Bridge
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 /opt/jns-management-bridge/server.py
Restart=on-failure
RestartSec=2
User=root
Group=root
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=read-only
ProtectSystem=strict
ReadOnlyPaths=/root/.ssh
ReadWritePaths=/etc/jns-management-bridge
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now jns-management-bridge

echo
echo "JNS Management Bridge installed."
echo "Local URL: http://127.0.0.1:8765/"
echo "Token:"
cat "$ETC_DIR/token"
echo
echo "Status:"
systemctl --no-pager --full status jns-management-bridge | sed -n '1,12p'
echo
echo "For a temporary HTTPS URL, use an authenticated/restricted tunnel of your choice."
