#!/bin/bash
set -Eeuo pipefail
test "$(hostname -s)" = nodec
ssh -o BatchMode=yes -o StrictHostKeyChecking=yes root@nodea.home.arpa 'bash -se' <<'HOST'
set -Eeuo pipefail
test "$(hostname -s)" = nodea
CT=250
if test -e /etc/pve/lxc/$CT.conf; then
  pct config "$CT" | grep -qx 'hostname: jns-mail' || { echo 'CT250 occupied; stopping'; exit 1; }
else
  test ! -e /etc/pve/qemu-server/$CT.conf
  pct create "$CT" local:vztmpl/debian-13-standard_13.6-1_amd64.tar.zst --hostname jns-mail --unprivileged 1 --cores 1 --memory 512 --swap 256 --rootfs vmdata:8 --net0 name=eth0,bridge=vmbr0,ip=dhcp,ip6=auto --nameserver 10.10.10.247 --searchdomain home.arpa --onboot 1 --description 'JNS lightweight mail: Postfix/Dovecot; two domains; no content scanning'
fi
pct status "$CT" | grep -q running || pct start "$CT"
for attempt in $(seq 1 30); do
  if pct exec "$CT" -- getent ahostsv4 deb.debian.org >/dev/null 2>&1; then break; fi
  sleep 2
done
pct exec "$CT" -- bash -se <<'GUEST'
set -Eeuo pipefail
export DEBIAN_FRONTEND=noninteractive
printf 'postfix postfix/main_mailer_type select Internet Site\npostfix postfix/mailname string mail.jnsystems.xyz\n' | debconf-set-selections
apt-get update -qq
apt-get install -y --no-install-recommends postfix dovecot-imapd dovecot-lmtpd opendkim opendkim-tools ca-certificates openssl python3
systemctl stop postfix dovecot opendkim
install -d -m 700 /root/jns-mail
if ! test -e /root/jns-mail/original-config.tar; then
  tar -cf /root/jns-mail/original-config.tar /etc/postfix /etc/dovecot /etc/opendkim.conf 2>/dev/null
fi
echo '=== VERSIONS ==='
dovecot --version
postconf mail_version
echo '=== NETWORK ==='
ip -brief address
ip route
echo '=== DOVECOT DEFAULT FILES ==='
head -35 /etc/dovecot/dovecot.conf
echo '=== MEMORY ==='
free -m
GUEST
HOST
