#!/usr/bin/env bash
set -Eeuo pipefail

ISO=/root/veyra-v0.9/Veyra-AutoInstall-v0.9.2.iso
EXPECTED=ee79d44d65cbad52bbf1c2c2a438cfdd99fc488234f54c24a0c80db6bfef0490
ROOT=/srv/veyra-pxe
TFTP=$ROOT/tftp
HTTP=$ROOT/http
REL=$HTTP/veyra/v0.9.2
PORT=8098
VEYRA_MAC=54:e1:ad:69:d1:8e

echo "=== VEYRA PXE v0.9.2 PREPARE ==="
date -Is
test -f "$ISO"
actual="$(sha256sum "$ISO" | awk '{print $1}')"
[[ "$actual" == "$EXPECTED" ]] || { echo "ISO SHA mismatch: $actual" >&2; exit 65; }

NODE_IP="$(ip -4 -o addr show dev vmbr0 scope global | awk '{split($4,a,"/"); print a[1]; exit}')"
[[ -n "$NODE_IP" ]] || { echo "Unable to determine Node C vmbr0 IPv4" >&2; exit 69; }
echo "node_ip=$NODE_IP"

if ss -lnt | awk '{print $4}' | grep -q ':8098$'; then
  existing="$(systemctl is-active veyra-pxe-http.service 2>/dev/null || true)"
  [[ "$existing" == active ]] || { echo "Port 8098 already in use by another service" >&2; exit 98; }
fi

need_apt=false
if ! command -v in.tftpd >/dev/null 2>&1 && [[ ! -x /usr/sbin/in.tftpd ]]; then
  need_apt=true
fi
if ! command -v dnsmasq >/dev/null 2>&1 && [[ ! -x /usr/sbin/dnsmasq ]]; then
  need_apt=true
fi
if [[ "$need_apt" == true ]]; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update
  if [[ ! -x /usr/sbin/in.tftpd ]]; then
    apt-get install -y --no-install-recommends tftpd-hpa
  fi
  if [[ ! -x /usr/sbin/dnsmasq ]]; then
    apt-get install -y --no-install-recommends dnsmasq-base
  fi
fi

test -f /usr/lib/ipxe/snponly.efi
test -f /usr/lib/ipxe/undionly.kpxe
command -v xorriso >/dev/null
command -v python3 >/dev/null

install -d -o root -g root -m 0755 "$TFTP" "$REL"
install -o root -g root -m 0644 /usr/lib/ipxe/snponly.efi "$TFTP/snponly.efi"
install -o root -g root -m 0644 /usr/lib/ipxe/undionly.kpxe "$TFTP/undionly.kpxe"
install -o root -g root -m 0644 "$ISO" "$REL/Veyra-AutoInstall-v0.9.2.iso"
printf '%s  %s\n' "$EXPECTED" "Veyra-AutoInstall-v0.9.2.iso" > "$REL/Veyra-AutoInstall-v0.9.2.sha256"

extract_one() {
  local dst="$1"; shift
  local src
  for src in "$@"; do
    if xorriso -indev "$ISO" -ls "$src" >/dev/null 2>&1; then
      rm -f "$dst"
      xorriso -osirrox on -indev "$ISO" -extract "$src" "$dst" >/dev/null 2>&1
      return 0
    fi
  done
  return 1
}

kernel_ok=false
initrd_ok=false
preseed_ok=false
extract_one "$REL/vmlinuz" /install.amd/vmlinuz /install/vmlinuz && kernel_ok=true || true
extract_one "$REL/initrd.gz" /install.amd/initrd.gz /install/initrd.gz && initrd_ok=true || true
extract_one "$REL/preseed.cfg" /preseed.cfg /veyra/preseed.cfg /config/preseed.cfg && preseed_ok=true || true

{
  echo '#!ipxe'
  echo "set server $NODE_IP"
  echo 'set base http://${server}:8098/veyra/v0.9.2'
  echo 'menu Veyra Network Deployment'
  echo 'item --key v veyra092 Veyra v0.9.2 Auto Install'
  echo 'item --key s shell iPXE shell'
  echo 'choose --default veyra092 --timeout 5000 target && goto ${target}'
  echo ':veyra092'
  echo 'echo Booting signed Veyra v0.9.2 from Node C...'
  echo 'sanboot --no-describe ${base}/Veyra-AutoInstall-v0.9.2.iso || goto installer'
  echo ':installer'
  if [[ "$kernel_ok" == true && "$initrd_ok" == true ]]; then
    if [[ "$preseed_ok" == true ]]; then
      echo 'kernel ${base}/vmlinuz auto=true priority=critical netcfg/choose_interface=auto url=${base}/preseed.cfg ---'
    else
      echo 'kernel ${base}/vmlinuz auto=true priority=critical netcfg/choose_interface=auto ---'
    fi
    echo 'initrd ${base}/initrd.gz'
    echo 'boot'
  else
    echo 'echo ISO SAN boot failed and no kernel/initrd fallback was found.'
    echo 'shell'
  fi
  echo ':shell'
  echo 'shell'
} > "$HTTP/autoexec.ipxe"

cp "$HTTP/autoexec.ipxe" "$TFTP/autoexec.ipxe"
chmod 0644 "$TFTP/"* "$HTTP/autoexec.ipxe" "$REL/"*

cat > /etc/default/tftpd-hpa <<EOF
TFTP_USERNAME="tftp"
TFTP_DIRECTORY="$TFTP"
TFTP_ADDRESS=":69"
TFTP_OPTIONS="--secure --create"
EOF

cat > /etc/systemd/system/veyra-pxe-http.service <<EOF
[Unit]
Description=Veyra PXE HTTP Server
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=nobody
Group=nogroup
WorkingDirectory=$HTTP
ExecStart=/usr/bin/python3 -m http.server $PORT --bind 0.0.0.0 --directory $HTTP
Restart=always
RestartSec=2
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadOnlyPaths=$HTTP

[Install]
WantedBy=multi-user.target
EOF

install -d -o root -g root -m 0755 /etc/veyra-pxe
cat > /etc/veyra-pxe/dnsmasq.conf <<EOF
port=0
interface=vmbr0
bind-dynamic
log-dhcp
dhcp-range=10.10.0.0,proxy
dhcp-mac=set:veyra,$VEYRA_MAC
dhcp-ignore=tag:!veyra
dhcp-userclass=set:ipxe,iPXE
dhcp-match=set:efi64,option:client-arch,7
dhcp-match=set:efi64,option:client-arch,9
dhcp-boot=tag:veyra,tag:ipxe,http://$NODE_IP:$PORT/autoexec.ipxe
dhcp-boot=tag:veyra,tag:!ipxe,tag:efi64,snponly.efi,,$NODE_IP
dhcp-boot=tag:veyra,tag:!ipxe,tag:!efi64,undionly.kpxe,,$NODE_IP
EOF

/usr/sbin/dnsmasq --test --conf-file=/etc/veyra-pxe/dnsmasq.conf

cat > /etc/systemd/system/veyra-pxe-proxydhcp.service <<EOF
[Unit]
Description=Veyra PXE ProxyDHCP
After=network-online.target tftpd-hpa.service
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/sbin/dnsmasq --keep-in-foreground --conf-file=/etc/veyra-pxe/dnsmasq.conf
Restart=always
RestartSec=2
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true

[Install]
WantedBy=multi-user.target
EOF

if ss -lunp 2>/dev/null | grep -E ':(67|4011)[[:space:]]' | grep -vq 'dnsmasq'; then
  echo "Unexpected existing DHCP/ProxyDHCP listener on Node C; refusing to collide" >&2
  ss -lunp 2>/dev/null | grep -E ':(67|4011)[[:space:]]' >&2 || true
  exit 98
fi

systemctl daemon-reload
systemctl enable tftpd-hpa.service
systemctl restart tftpd-hpa.service
systemctl enable --now veyra-pxe-http.service
systemctl enable --now veyra-pxe-proxydhcp.service
systemctl restart veyra-pxe-proxydhcp.service
sleep 2

systemctl is-active --quiet tftpd-hpa.service
systemctl is-active --quiet veyra-pxe-http.service
systemctl is-active --quiet veyra-pxe-proxydhcp.service
ss -lun | grep -q ':69 '
ss -lun | grep -q ':67 '
ss -lnt | grep -q ':8098 '

curl -fsS "http://127.0.0.1:$PORT/autoexec.ipxe" >/dev/null
curl -fsS "http://127.0.0.1:$PORT/veyra/v0.9.2/Veyra-AutoInstall-v0.9.2.sha256" | grep -q "$EXPECTED"
curl -fsSI "http://127.0.0.1:$PORT/veyra/v0.9.2/Veyra-AutoInstall-v0.9.2.iso" >/dev/null

if command -v tftp >/dev/null 2>&1; then
  tmp="$(mktemp -d)"
  (cd "$tmp" && timeout 8 tftp 127.0.0.1 -m binary -c get snponly.efi >/dev/null 2>&1)
  cmp -s "$tmp/snponly.efi" "$TFTP/snponly.efi"
  rm -rf "$tmp"
fi

echo "=== PXE READY ==="
echo "TFTP server: $NODE_IP:69"
echo "UEFI bootfile: snponly.efi"
echo "BIOS bootfile: undionly.kpxe"
echo "iPXE script: http://$NODE_IP:$PORT/autoexec.ipxe"
echo "ISO: http://$NODE_IP:$PORT/veyra/v0.9.2/Veyra-AutoInstall-v0.9.2.iso"
echo "sha256=$EXPECTED"
echo "kernel_fallback=$kernel_ok initrd_fallback=$initrd_ok preseed=$preseed_ok"
echo "ProxyDHCP target MAC: $VEYRA_MAC"
echo "VEYRA_PXE_V092_READY"
