#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/jns-management-bridge"
ETC_DIR="/etc/jns-management-bridge"
SERVICE="/etc/systemd/system/jns-management-bridge.service"
RUN_USER="${JNS_BRIDGE_USER:-${SUDO_USER:-root}}"
RUN_GROUP="$(id -gn "$RUN_USER")"
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
install -d -m 0750 -o "$RUN_USER" -g "$RUN_GROUP" "$ETC_DIR"

curl -fsSL "$BASE/server.py" -o "$APP_DIR/server.py"
curl -fsSL "$BASE/start_temp_tunnel.sh" -o "$APP_DIR/start_temp_tunnel.sh"
curl -fsSL "$BASE/stop_temp_tunnel.sh" -o "$APP_DIR/stop_temp_tunnel.sh"
chmod 0755 "$APP_DIR/server.py" "$APP_DIR/start_temp_tunnel.sh" "$APP_DIR/stop_temp_tunnel.sh"

if [[ ! -f "$ETC_DIR/config.json" ]]; then
  curl -fsSL "$BASE/config.example.json" -o "$ETC_DIR/config.json"
  chown "$RUN_USER:$RUN_GROUP" "$ETC_DIR/config.json"
  chmod 0600 "$ETC_DIR/config.json"
  echo "Created $ETC_DIR/config.json — edit targets before relying on SSH mode."
fi

if [[ ! -s "$ETC_DIR/token" ]]; then
  umask 077
  openssl rand -hex 32 > "$ETC_DIR/token"
fi
chown "$RUN_USER:$RUN_GROUP" "$ETC_DIR/token"
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
User=__RUN_USER__
Group=__RUN_GROUP__
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=read-only
ProtectSystem=strict
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF
sed -i "s/__RUN_USER__/$RUN_USER/g; s/__RUN_GROUP__/$RUN_GROUP/g" "$SERVICE"

systemctl daemon-reload
systemctl enable --now jns-management-bridge

echo
echo "JNS Management Bridge installed."
echo "Service account: $RUN_USER"
echo "Local URL: http://127.0.0.1:8765/"
echo "Token:"
cat "$ETC_DIR/token"
echo
echo "Status:"
systemctl --no-pager --full status jns-management-bridge | sed -n '1,12p'
echo
echo "Start a temporary HTTPS session with:"
echo "  sudo $APP_DIR/start_temp_tunnel.sh"
echo "Stop it afterwards with:"
echo "  sudo $APP_DIR/stop_temp_tunnel.sh"
