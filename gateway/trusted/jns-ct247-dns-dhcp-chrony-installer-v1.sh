#!/usr/bin/env bash
# JNS CT247 DNS/DHCP/NTP installer. Interactive; --check is read-only.
set -Eeuo pipefail
[[ $(id -u) -eq 0 ]] || { echo "Run as root inside CT247"; exit 1; }
[[ $(hostname) != nodec ]] || { echo "Refusing on Proxmox host"; exit 1; }
[[ ${1:-} == --check ]] && {
  hostname; ip -4 -br addr; findmnt -t nfs,nfs4; systemctl is-active jns-dns dnsmasq chrony ssh 2>/dev/null || :; exit 0;
}
[[ ${1:-} == --install ]] || { echo "Usage: $0 --check | --install"; exit 2; }
echo "JNS CT247 installer. DHCP/DNS service restart is required after confirmation."
read -r -p "Existing WD NAS NFS mount path INSIDE CT247: " NFS
[[ -d "$NFS" && "$NFS" == /* && "$NFS" != / ]] || { echo "Invalid path"; exit 2; }
findmnt -T "$NFS" -n -o FSTYPE | grep -Eq '^nfs4?$' || { echo "STOP: NFS is not mounted"; exit 2; }
read -r -p "IPv6 /64 ULA prefix [fda6:8b55:d590::/64]: " PREFIX
PREFIX=${PREFIX:-fda6:8b55:d590::/64}
[[ "$PREFIX" == 'fda6:8b55:d590::/64' ]] || { echo "STOP: review new IPv6 prefix before use"; exit 2; }
read -r -p "Type INSTALL-CT247 to prepare the new service: " YES
[[ "$YES" == INSTALL-CT247 ]] || exit 2
echo "Install openssh-server chrony dnsmasq and Python stdlib. No router settings changed."
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y dnsmasq chrony openssh-server
systemctl stop dnsmasq 2>/dev/null || true
install -d -m 0750 "$NFS/jns-network" "$NFS/jns-network/leases" "$NFS/jns-network/config"
CFG="$NFS/jns-network/config"
LEASE="$NFS/jns-network/leases/ct247.leases"
touch "$LEASE"
[[ -f "$CFG/static-mac-ipv4.csv" ]] || cat > "$CFG/static-mac-ipv4.csv" <<'CSV'
# MAC,IPv4,hostname  (infrastructure only; lower-case DNS name without .home.arpa)
# 00:11:22:33:44:55,10.10.254.250,switch
CSV
[[ -f "$CFG/static-hosts.txt" ]] || cat > "$CFG/static-hosts.txt" <<'HOSTS'
# One address and one or more names per line
10.10.254.254 router.home.arpa router
HOSTS
[[ -f "$CFG/protected-ipv4.txt" ]] || cat > "$CFG/protected-ipv4.txt" <<'IP'
# Infrastructure exclusions: add ALL other infrastructure/static IPs before enabling DHCP.
10.10.254.254
10.10.110.247
10.10.110.248
10.10.110.249
10.10.110.255
IP
echo "Edit these files on the NAS BEFORE activating:"
printf '%s\n' "$CFG/static-mac-ipv4.csv" "$CFG/protected-ipv4.txt" "$CFG/static-hosts.txt"
cat > /usr/local/sbin/jns-ct247-render <<'PY'
#!/usr/bin/env python3
import csv, ipaddress, pathlib, sys
cfg=pathlib.Path(sys.argv[1]); out=pathlib.Path(sys.argv[2])
net=ipaddress.IPv4Network('10.10.0.0/16')
protected={int(net.network_address),int(net.broadcast_address)}
for line in (cfg/'protected-ipv4.txt').read_text().splitlines():
 s=line.partition('#')[0].strip()
 if s:
  x=ipaddress.IPv4Address(s)
  if x in net: protected.add(int(x))
reservations=[]
for row in csv.reader((cfg/'static-mac-ipv4.csv').open()):
 if not row or row[0].strip().startswith('#'): continue
 if len(row)!=3: raise ValueError('Expected MAC,IPv4,hostname')
 mac,addr,host=[i.strip() for i in row]
 ip=ipaddress.IPv4Address(addr)
 if ip not in net: raise ValueError('reservation outside /16')
 if not all(c.isascii() and (c.isalnum() or c=='-') for c in host): raise ValueError('bad hostname')
 protected.add(int(ip)); reservations.append((mac,addr,host))
# Always protect host's own existing IPv4 and the current static hosts list.
for line in (cfg/'static-hosts.txt').read_text().splitlines():
 s=line.partition('#')[0].split()
 if s:
  try:
   ip=ipaddress.ip_address(s[0])
   if isinstance(ip,ipaddress.IPv4Address) and ip in net: protected.add(int(ip))
  except ValueError: raise ValueError('invalid static hosts address')
for p in pathlib.Path('/proc/net/fib_trie').read_text().splitlines():
 pass
lines=['port=53','interface=eth0','bind-dynamic','no-resolv','server=1.1.1.1','server=9.9.9.9',
 'domain=home.arpa','local=/home.arpa/','expand-hosts','dhcp-authoritative',
 'dhcp-option=option:router,10.10.254.254',
 'dhcp-option=option:dns-server,10.10.110.247,10.10.110.248',
 'dhcp-leasefile='+sys.argv[3],'addn-hosts='+str(cfg/'static-hosts.txt'),
 'dhcp-hostsfile='+str(out.parent/'static-hosts.dhcp'),
 'log-dhcp']
# Range deliberately split around ALL protected addresses: do not allocate existing infrastructure.
first=int(net.network_address)+1
for p in sorted(protected):
 if p>first:
  lines.append(f'dhcp-range={ipaddress.IPv4Address(first)},{ipaddress.IPv4Address(p-1)},255.255.0.0,12h')
 first=max(first,p+1)
if first<int(net.broadcast_address): lines.append(f'dhcp-range={ipaddress.IPv4Address(first)},{ipaddress.IPv4Address(int(net.broadcast_address)-1)},255.255.0.0,12h')
# ULA /64; DHCPv6 with RA for clients supporting stateful DHCPv6; SLAAC is retained.
lines+=['enable-ra','dhcp-range=fda6:8b55:d590::1000,fda6:8b55:d590::ffff,64,12h',
 'dhcp-option=option6:dns-server,[fda6:8b55:d590::247],[fda6:8b55:d590::248]']
out.write_text('\n'.join(lines)+'\n')
(out.parent/'static-hosts.dhcp').write_text(''.join(','.join(r)+'\n' for r in reservations))
print(f'Rendered {len(reservations)} reservations and {sum(x.startswith("dhcp-range=") for x in lines)} ranges')
PY
chmod 755 /usr/local/sbin/jns-ct247-render
# Protect the host's active IPv4 address from the full /16 pool.
ip -4 -o addr show dev eth0 | awk '{print $4}' | cut -d/ -f1 >> "$CFG/protected-ipv4.txt"
BACKUP="/root/jns-ct247-preinstall-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$BACKUP"
cp -a /etc/dnsmasq.conf "$BACKUP/dnsmasq.conf"
systemctl cat jns-dns.service > "$BACKUP/jns-dns.service.txt" 2>/dev/null || true
mkdir -p /etc/jns-ct247
/usr/local/sbin/jns-ct247-render "$CFG" /etc/jns-ct247/dnsmasq.conf "$LEASE"
dnsmasq --test -C /etc/jns-ct247/dnsmasq.conf
echo "Configuration compiled, existing service still untouched. Backup: $BACKUP"
echo "Inspect: cat /etc/jns-ct247/dnsmasq.conf"
read -r -p "Type ACTIVATE to switch CT247 DHCP/DNS service: " GO
[[ "$GO" == ACTIVATE ]] || { echo "Prepared only, no DHCP/DNS switch"; exit 0; }
cat > /etc/systemd/system/jns-ct247.service <<'UNIT'
[Unit]
Description=JNS CT247 DNS and DHCPv4/DHCPv6
After=network-online.target remote-fs.target
RequiresMountsFor=/mnt
[Service]
Type=simple
ExecStartPre=/usr/sbin/dnsmasq --test -C /etc/jns-ct247/dnsmasq.conf
ExecStart=/usr/sbin/dnsmasq --keep-in-foreground -C /etc/jns-ct247/dnsmasq.conf
Restart=on-failure
[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl disable --now jns-dns.service dnsmasq.service 2>/dev/null || true
systemctl enable --now jns-ct247.service
systemctl enable --now chrony ssh
echo "Set root password locally (password is never sent to GitHub or ChatGPT):"
passwd root
mkdir -p /etc/ssh/sshd_config.d
printf 'PermitRootLogin yes\nPasswordAuthentication yes\n' > /etc/ssh/sshd_config.d/00-jns-root.conf
sshd -t && systemctl reload ssh
echo "=== FINAL ==="
systemctl is-active jns-ct247.service chrony ssh
echo "Backup: $BACKUP"
echo "NFS shared files: $CFG and $LEASE"
echo "NOTE: DHCPv6 address registration needs suitable client DHCPv6 usage and effective RA flags."
