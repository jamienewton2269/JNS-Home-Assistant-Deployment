#!/usr/bin/env bash
set -Eeuo pipefail
[[ $(id -u) -eq 0 ]] || { echo 'Run as root on Node C'; exit 77; }
ROOT=/srv/veyra-pxe/http
D=$ROOT/veyra/v0.9.2-netboot
SEED=$D/preseed-auto.cfg
LOGS=$ROOT/veyra/install-logs
test -s "$SEED"
grep -Fq 'partman/early_command' "$SEED"
grep -Fq 'WDCWD10SPZX-24Z10T0' "$SEED"
BEFORE=$(sha256sum "$ROOT/autoexec.ipxe" /srv/veyra-pxe/tftp/autoexec.ipxe "$D/vmlinuz" "$D/initrd.gz")
if ss -Hlun | grep -q ':5514 '; then echo 'STOP: UDP 5514 already in use'; exit 78; fi
B=/srv/veyra-pxe/backups/veyra-logging-$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p "$B" "$LOGS"
cp -a "$SEED" "$B/preseed-auto.cfg"
chmod 0755 "$LOGS"
cat > "$LOGS/relay.sh" <<'RELAY'
#!/bin/sh
# Automatically executed by Debian installer before disk check.
set +e
TX=$(command -v nc 2>/dev/null)
send() {
 logger -t veyra-installer "$1" 2>/dev/null
 if [ -n "$TX" ]; then
  printf '%s\n' "veyra-installer: $1" | "$TX" -u -w 2 10.10.110.13 5514 >/dev/null 2>&1
 fi
}
send 'INSTALLER_EARLY_LOG_START'
send "KERNEL=$(uname -r)"
send "BLOCKS=$(ls /sys/block 2>/dev/null | tr '\n' ' ')"
for b in /sys/block/sd* /sys/block/nvme*n*; do
 [ -e "$b" ] || continue
 model=$(cat "$b/device/model" 2>/dev/null)
 send "DISK=$(basename "$b") MODEL=$model"
done
if [ -n "$TX" ]; then
 (tail -n +1 -f /var/log/syslog 2>/dev/null | "$TX" -u 10.10.110.13 5514 >/dev/null 2>&1) &
 send 'SYSLOG_PIPE_ACTIVE'
else
 logger -t veyra-installer 'ERROR: netcat unavailable'
fi
exit 0
RELAY
chmod 0644 "$LOGS/relay.sh"
cat > /usr/local/sbin/veyra-udp-install-logger.py <<'PY'
#!/usr/bin/env python3
import datetime,os,socket
from pathlib import Path
root=Path('/srv/veyra-pxe/http/veyra/install-logs')
sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
sock.bind(('0.0.0.0',5514))
print('VEYRA_LOG_RECEIVER_READY',flush=True)
while True:
 data,peer=sock.recvfrom(65535)
 if not (peer[0].startswith('10.10.') or peer[0]=='127.0.0.1'): continue
 path=root/'latest.log'
 if path.exists() and path.stat().st_size>32*1024*1024: path.replace(root/'previous.log')
 stamp=datetime.datetime.now(datetime.timezone.utc).isoformat()
 with path.open('ab') as output:
  os.chmod(path,0o644)
  output.write((stamp+' '+peer[0]+' ').encode()+data.rstrip(b'\r\n')+b'\n')
PY
chmod 0755 /usr/local/sbin/veyra-udp-install-logger.py
cat > /etc/systemd/system/veyra-udp-install-logger.service <<'UNIT'
[Unit]
Description=Veyra Debian Installer Text Log Receiver
After=network.target
[Service]
ExecStart=/usr/bin/python3 -u /usr/local/sbin/veyra-udp-install-logger.py
Restart=always
RestartSec=3
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=/srv/veyra-pxe/http/veyra/install-logs
[Install]
WantedBy=multi-user.target
UNIT
python3 - "$SEED" "$B/new-preseed.cfg" <<'PY'
from pathlib import Path
import sys
src,dst=map(Path,sys.argv[1:])
lines=src.read_text().splitlines()
key='d-i preseed/early_command string '
hook='wget -q -O /tmp/veyra-log-relay.sh http://10.10.110.13:8098/veyra/install-logs/relay.sh && sh /tmp/veyra-log-relay.sh'
lines=[line for line in lines if not line.startswith(key)]
lines.insert(0,key+hook)
dst.write_text('\n'.join(lines)+'\n')
assert 'partman/early_command' in dst.read_text()
assert 'WDCWD10SPZX-24Z10T0' in dst.read_text()
assert 'veyra-payload.tar.gz' in dst.read_text()
PY
systemctl daemon-reload
systemctl enable --now veyra-udp-install-logger.service
systemctl is-active --quiet veyra-udp-install-logger.service
ss -lun | grep -q ':5514 '
install -m 0644 "$B/new-preseed.cfg" "$SEED.next"
mv -f "$SEED.next" "$SEED"
curl -fsS 'http://127.0.0.1:8098/veyra/v0.9.2-netboot/preseed-auto.cfg' | grep -Fq 'veyra-log-relay.sh'
curl -fsS 'http://127.0.0.1:8098/veyra/install-logs/relay.sh' | grep -Fq 'SYSLOG_PIPE_ACTIVE'
python3 - <<'PY'
import socket
s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
s.sendto(b'VEYRA_LOG_RECEIVER_SELFTEST',('127.0.0.1',5514))
PY
sleep 1
curl -fsS 'http://127.0.0.1:8098/veyra/install-logs/latest.log' | grep -Fq VEYRA_LOG_RECEIVER_SELFTEST
test "$BEFORE" = "$(sha256sum "$ROOT/autoexec.ipxe" /srv/veyra-pxe/tftp/autoexec.ipxe "$D/vmlinuz" "$D/initrd.gz")"
echo VEYRA_INSTALL_LOGGING_READY
echo LOG_URL=http://10.10.110.13:8098/veyra/install-logs/latest.log
echo "ROLLBACK_PRESEED=$B/preseed-auto.cfg"
echo PXE_MENU_KERNEL_AND_FIRMWARE_UNCHANGED
