#!/usr/bin/env bash
# Persistent passive UDP receiver for Veyra Debian installer debugging.
# Does not alter PXE, network, installer, or disk settings.
set -Eeuo pipefail
[[ "$(id -u)" == 0 ]] || { echo 'STOP: root required on Node C'; exit 77; }
if ss -Hlun '( sport = :5514 )' | grep -q .; then
  echo 'STOP: UDP/5514 has an existing listener; refusing to replace it'
  ss -lunp | grep ':5514' || true
  exit 78
fi
install -d -m 0750 /var/log/veyra-installer
cat > /usr/local/sbin/veyra-installer-udp-logger.py <<'PY'
#!/usr/bin/env python3
import datetime
import os
import socket
from pathlib import Path
dest=Path('/var/log/veyra-installer/installer-udp5514.log')
sock=socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(('0.0.0.0', 5514))
print('VEYRA_SYSLOG_UDP_5514_LISTENING', flush=True)
with dest.open('ab', buffering=0) as fp:
    os.chmod(dest,0o640)
    while True:
        data,addr=sock.recvfrom(65535)
        ts=datetime.datetime.now(datetime.timezone.utc).isoformat()
        fp.write((ts+' '+addr[0]+' ').encode()+data.rstrip(b'\r\n')+b'\n')
PY
chmod 0755 /usr/local/sbin/veyra-installer-udp-logger.py
cat >/etc/systemd/system/veyra-installer-syslog.service <<'UNIT'
[Unit]
Description=Veyra Debian installer UDP 5514 diagnostic log recorder
After=network.target
[Service]
Type=simple
ExecStart=/usr/bin/python3 -u /usr/local/sbin/veyra-installer-udp-logger.py
Restart=always
RestartSec=2
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=/var/log/veyra-installer
[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now veyra-installer-syslog.service
systemctl is-active --quiet veyra-installer-syslog.service
ss -lunp | grep ':5514'
echo 'VEYRA_SYSLOG_RECEIVER_READY'
echo 'LOG=/var/log/veyra-installer/installer-udp5514.log'
echo 'VIEW=tail -n 100 -f /var/log/veyra-installer/installer-udp5514.log'
