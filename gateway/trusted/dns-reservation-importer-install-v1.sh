#!/usr/bin/env bash
set -Eeuo pipefail
[ "$(id -u)" -eq 0 ] || { echo "run as root"; exit 77; }
SRC_ROOT="${JNS_REPO_ROOT:-}"
if [ -z "$SRC_ROOT" ]; then
  echo "JNS_REPO_ROOT is required when invoked from the trusted handler" >&2
  exit 78
fi
[ -f "$SRC_ROOT/management_bridge/dns_reservation_importer.py" ] || {
  echo "Importer source missing under $SRC_ROOT" >&2
  exit 79
}
[ -f "$SRC_ROOT/management_bridge/jns-dns-static-apply.py" ] || {
  echo "DNS apply helper source missing under $SRC_ROOT" >&2
  exit 80
}
install -d -o root -g root -m 0755 /usr/local/libexec
install -o root -g root -m 0755 "$SRC_ROOT/management_bridge/dns_reservation_importer.py" /usr/local/libexec/jns-dns-reservation-importer
install -o root -g root -m 0755 "$SRC_ROOT/management_bridge/jns-dns-static-apply.py" /usr/local/sbin/jns-dns-static-apply
cat >/etc/systemd/system/jns-dns-reservation-importer.service <<'EOF'
[Unit]
Description=JNS DrayTek DNS Reservation Importer
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 /usr/local/libexec/jns-dns-reservation-importer
Restart=on-failure
RestartSec=2
Environment=JNS_DNS_PRIMARY=10.10.10.247
Environment=JNS_DNS_SECONDARY=10.10.10.248
Environment=JNS_DNS_DOMAIN=home.arpa

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now jns-dns-reservation-importer
sleep 1
systemctl is-active --quiet jns-dns-reservation-importer
curl -fsS --max-time 5 http://127.0.0.1:8770/health
echo
echo "DNS reservation importer installed on Node C: http://$(hostname -I | awk '{print $1}'):8770/"
