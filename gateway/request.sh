#!/usr/bin/env bash
set -euo pipefail
echo "=== APPLY AUDIO STATIC IP + LAN DNS ==="
date -Is

apply_audio_ip() {
  H="$1"; ID="$2"; IP="$3"
  echo "=== $H VM$ID -> $IP ==="
  ssh -o BatchMode=yes "$H" "qm guest exec $ID -- /bin/bash -lc 'cp -a /etc/systemd/network /root/systemd-network.pre-jns-$(date +%Y%m%d-%H%M%S) 2>/dev/null || true; cat > /etc/systemd/network/05-jns-static-ens18.network <<EOF
[Match]
Name=ens18

[Network]
Address=$IP/24
Gateway=10.10.10.254
DNS=10.10.10.247
DNS=10.10.10.248
Domains=home.arpa
DHCP=no
IPv6AcceptRA=yes
EOF
systemctl enable systemd-networkd >/dev/null 2>&1 || true
systemctl restart systemd-networkd
sleep 2
ip -br -4 addr show ens18
ip route
cat /etc/resolv.conf
'"
  sleep 2
  ping -c2 -W1 "$IP"
}

apply_audio_ip nodea 214 10.10.10.228
apply_audio_ip nodeb 219 10.10.10.229

echo "=== VERIFY ACTIVE/STANDBY BLUETOOTH FENCING ==="
ssh -o BatchMode=yes nodea "qm guest exec 214 -- /bin/bash -lc 'systemctl is-enabled house-audio-reconnect.timer; bluetoothctl info 73:81:7B:84:2A:AB 2>/dev/null | grep -E \"Name:|Paired:|Trusted:|Connected:\"'"
ssh -o BatchMode=yes nodeb "qm guest exec 219 -- /bin/bash -lc 'systemctl is-enabled house-audio-reconnect.timer || true; bluetoothctl devices 2>/dev/null || true'"

echo "=== UPDATE DNS A + B ==="
for pair in "nodea 217" "nodeb 218"; do
  set -- $pair; H=$1; CT=$2
  echo "--- $H CT$CT ---"
  ssh -o BatchMode=yes "$H" "pct exec $CT -- python3 - <<'PY'
from pathlib import Path
import shutil,time
p=Path('/opt/AdGuardHome/AdGuardHome.yaml')
s=p.read_text()
backup=p.with_name(p.name+'.pre-house-audio-'+time.strftime('%Y%m%d-%H%M%S'))
shutil.copy2(p,backup)
entries=[
 ('house-audio-a.home.arpa','10.10.10.228'),
 ('house-audio-a','10.10.10.228'),
 ('house-audio-b.home.arpa','10.10.10.229'),
 ('house-audio-b','10.10.10.229'),
]
for domain,answer in entries:
    if f'    - domain: {domain}\n      answer: {answer}\n' in s:
        continue
    marker='  rewrites:\n'
    pos=s.find(marker)
    if pos < 0:
        raise SystemExit('rewrites section missing')
    insert=pos+len(marker)
    s=s[:insert]+f'    - domain: {domain}\n      answer: {answer}\n'+s[insert:]
p.write_text(s)

u=Path('/etc/unbound/unbound.conf.d/home-arpa.conf')
us=u.read_text() if u.exists() else 'server:\n'
ub=u.with_name(u.name+'.pre-house-audio-'+time.strftime('%Y%m%d-%H%M%S'))
if u.exists(): shutil.copy2(u,ub)
for host,ip in [('house-audio-a.home.arpa.','10.10.10.228'),('house-audio-b.home.arpa.','10.10.10.229')]:
    line=f'  local-data: "{host} 60 IN A {ip}"'
    if line not in us: us += ('\n' if not us.endswith('\n') else '')+line+'\n'
u.write_text(us)
print('updated',p,backup,u)
PY
pct exec $CT -- systemctl restart unbound
pct exec $CT -- systemctl restart AdGuardHome
pct exec $CT -- systemctl --no-pager --full is-active unbound AdGuardHome
"
done

echo "=== DNS VERIFY ==="
for dns in 10.10.10.247 10.10.10.248; do
  echo "DNS $dns"
  for n in house-audio-a.home.arpa house-audio-b.home.arpa; do
    getent ahostsv4 "$n" >/dev/null 2>&1 || true
    dig +short @"$dns" "$n" A
  done
done
