#!/usr/bin/env bash
set -Eeuo pipefail
test "$(id -u)" -eq 0 || exit 77
ROOT=/srv/veyra-pxe/http
D=$ROOT/veyra/v0.9.2-netboot
S=$D/preseed-auto.cfg
L=$ROOT/veyra/install-logs
test -s "$S" && test -s "$D/vmlinuz" && test -s "$D/initrd.gz"
grep -Fq WDCWD10SPZX-24Z10T0 "$S"
H0=$(sha256sum "$ROOT/autoexec.ipxe" /srv/veyra-pxe/tftp/autoexec.ipxe "$D/vmlinuz" "$D/initrd.gz")
ss -Hlun | grep -q ':5515 ' && { echo 'STOP: UDP 5515 already occupied'; exit 78; }
B=/srv/veyra-pxe/backups/veyra-safe-disk-$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p "$B" "$L"
chmod 0755 "$L"
cp -a "$S" "$B/preseed-auto.cfg"
cat > "$L/probe.sh" <<'PROBE'
#!/bin/sh
set +e
send() {
 logger -t veyra-disk "$1" 2>/dev/null
 printf '%s\n' "veyra-disk: $1" | nc -u -w 2 10.10.110.13 5515 >/dev/null 2>&1
}
send "DISK_PROBE_START $(date)"
count=0
target=''
for b in /sys/block/sd* /sys/block/nvme*n* /sys/block/vd*; do
 [ -d "$b" ] || continue
 name=$(basename "$b")
 [ -b "/dev/$name" ] || continue
 removable=$(cat "$b/removable" 2>/dev/null)
 sectors=$(cat "$b/size" 2>/dev/null)
 model=$(cat "$b/device/model" 2>/dev/null)
 path=$(readlink -f "$b/device" 2>/dev/null)
 send "FOUND name=$name model=$model removable=$removable sectors=$sectors path=$path"
 [ "$removable" = 0 ] || { send "REJECT $name removable"; continue; }
 case "$path" in *usb*) send "REJECT $name USB"; continue;; esac
 case "$sectors" in ''|*[!0-9]*) send "REJECT $name invalid-size"; continue;; esac
 [ "$sectors" -ge 33554432 ] || { send "REJECT $name too-small"; continue; }
 count=$((count+1))
 target="/dev/$name"
done
if [ "$count" -ne 1 ]; then send "FATAL disk selection ambiguous count=$count"; exit 1; fi
send "ACCEPTED $target single internal non-removable disk"
debconf-set partman-auto/disk "$target" || { send "FATAL unable to set partman disk"; exit 1; }
send "DISK_SELECTED $target"
exit 0
PROBE
cat > "$L/early.sh" <<'EARLY'
#!/bin/sh
logger -t veyra-installer 'EARLY_INSTALL_LOG_START' 2>/dev/null
printf 'veyra-installer: EARLY_INSTALL_LOG_START\n' | nc -u -w 2 10.10.110.13 5515 >/dev/null 2>&1
(tail -n +1 -f /var/log/syslog 2>/dev/null | nc -u 10.10.110.13 5515 >/dev/null 2>&1) &
exit 0
EARLY
chmod 0644 "$L/probe.sh" "$L/early.sh"
cat >/usr/local/sbin/veyra-udp-5515.py <<'PY'
#!/usr/bin/env python3
import datetime,os,socket
from pathlib import Path
d=Path('/srv/veyra-pxe/http/veyra/install-logs')
s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
s.bind(('0.0.0.0',5515))
while True:
 b,addr=s.recvfrom(65535)
 if not (addr[0]=='127.0.0.1' or addr[0].startswith('10.10.')):continue
 p=d/'latest.log'
 if p.exists() and p.stat().st_size>32*1024*1024:p.replace(d/'previous.log')
 with p.open('ab') as f:
  os.chmod(p,0o644)
  f.write((datetime.datetime.now(datetime.timezone.utc).isoformat()+' '+addr[0]+' ').encode()+b.rstrip(b'\r\n')+b'\n')
PY
chmod 0755 /usr/local/sbin/veyra-udp-5515.py
cat >/etc/systemd/system/veyra-udp-5515.service <<'UNIT'
[Unit]
Description=Veyra Installer Diagnostic Text UDP 5515
After=network.target
[Service]
ExecStart=/usr/bin/python3 -u /usr/local/sbin/veyra-udp-5515.py
Restart=always
RestartSec=3
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=/srv/veyra-pxe/http/veyra/install-logs
[Install]
WantedBy=multi-user.target
UNIT
python3 - "$S" "$B/next.cfg" <<'PY'
from pathlib import Path
import sys
src,dst=map(Path,sys.argv[1:])
s=src.read_text()
start=s.index('d-i partman/early_command string \\')
end=s.index('\n',s.index('\n',start)+1)
old=s[start:end]
assert 'WDCWD10SPZX-24Z10T0' in old
replacement='d-i partman/early_command string wget -q -O /tmp/veyra-disk-probe.sh http://10.10.110.13:8098/veyra/install-logs/probe.sh && sh /tmp/veyra-disk-probe.sh'
s=s[:start]+replacement+s[end:]
s='\n'.join(x for x in s.splitlines() if not x.startswith('d-i preseed/early_command string '))
s='d-i preseed/early_command string wget -q -O /tmp/veyra-early.sh http://10.10.110.13:8098/veyra/install-logs/early.sh && sh /tmp/veyra-early.sh\n'+s+'\n'
s=s.replace('d-i partman-auto/disk string /dev/sda','d-i partman-auto/disk string /dev/disk/by-id/veyra-dynamic-selection')
assert s.count('d-i partman/early_command string')==1
assert 'veyra-payload.tar.gz' in s
dst.write_text(s)
PY
systemctl daemon-reload
systemctl enable --now veyra-udp-5515.service
systemctl is-active --quiet veyra-udp-5515.service
python3 - <<'PY'
import socket
s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
s.sendto(b'VEYRA_5515_SELFTEST',('127.0.0.1',5515))
PY
sleep 1
curl -fsS 'http://127.0.0.1:8098/veyra/install-logs/latest.log' | grep -Fq VEYRA_5515_SELFTEST
for f in probe.sh early.sh; do curl -fsS -o /dev/null "http://127.0.0.1:8098/veyra/install-logs/$f"; done
install -m 0644 "$B/next.cfg" "$S.next"
mv -f "$S.next" "$S"
test "$H0" = "$(sha256sum "$ROOT/autoexec.ipxe" /srv/veyra-pxe/tftp/autoexec.ipxe "$D/vmlinuz" "$D/initrd.gz")"
echo VEYRA_DISK_SAFETY_LOGGING_READY
echo http://10.10.110.13:8098/veyra/install-logs/latest.log
echo "BACKUP=$B"
