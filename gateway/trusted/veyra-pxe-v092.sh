#!/usr/bin/env bash
set -Eeuo pipefail

ISO=/root/veyra-v0.9/Veyra-AutoInstall-v0.9.2.iso
EXPECTED=53e31c84dc0613773e1224215e03004423d3daaaf5ff6cbd518dd1f17f15e246
ROOT=/srv/veyra-pxe
TFTP=$ROOT/tftp
HTTP=$ROOT/http
REL=$HTTP/veyra/v0.9.2
PORT=8098
VEYRA_MAC=54:e1:ad:69:d1:8e
SOURCE_PAYLOAD=/root/veyra-v0.9/source071/veyra
DEBIAN_NETBOOT_BASE=https://deb.debian.org/debian/dists/trixie/main/installer-amd64/current/images/netboot/debian-installer/amd64
DEBIAN_FW_INDEX=https://deb.debian.org/debian/dists/trixie/non-free-firmware/binary-amd64/Packages.xz
DEBIAN_MIRROR=https://deb.debian.org/debian

echo "=== VEYRA PXE v0.9.2 PREPARE ==="
date -Is
test -f "$ISO"
test -d "$SOURCE_PAYLOAD"
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
for cmd in wget cpio gzip xz dpkg-deb; do
  command -v "$cmd" >/dev/null 2>&1 || {
    export DEBIAN_FRONTEND=noninteractive
    apt-get update
    apt-get install -y --no-install-recommends wget cpio gzip xz-utils dpkg
    break
  }
done

# Preserve the exact currently published boot files before any change.
BACKUP="$ROOT/backups/veyra-v092-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$BACKUP"
for filename in autoexec.ipxe; do
  test -f "$HTTP/$filename" && cp -a "$HTTP/$filename" "$BACKUP/$filename" || true
done
for filename in vmlinuz initrd.gz preseed.cfg veyra-payload.tar.gz; do
  test -f "$REL/$filename" && cp -a "$REL/$filename" "$BACKUP/$filename" || true
done
echo "VEYRA_PRE_PUBLICATION_BACKUP=$BACKUP"

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

if [[ "$kernel_ok" == true && "$initrd_ok" == true ]]; then
  cp -f "$REL/vmlinuz" "$REL/vmlinuz-cd"
  cp -f "$REL/initrd.gz" "$REL/initrd-cd.gz"

  work="$(mktemp -d)"
  trap 'rm -rf "$work"' EXIT

  # The Veyra ISO is the authoritative, hardware-proven installer. Never
  # substitute a generic Debian netboot kernel or initrd here.
  echo "ISO_MATCHED_KERNEL_SHA256=$(sha256sum "$REL/vmlinuz" | awk '{print $1}')"
  echo "ISO_MATCHED_INITRD_SHA256=$(sha256sum "$REL/initrd.gz" | awk '{print $1}')"
  echo "VEYRA_ORIGINAL_ISO_INSTALLER_PRESERVED"
fi

if [[ "$preseed_ok" == true ]]; then
  cp "$REL/preseed.cfg" "$REL/preseed-iso.cfg"
  tar -C "$(dirname "$SOURCE_PAYLOAD")" -czf "$REL/veyra-payload.tar.gz" "$(basename "$SOURCE_PAYLOAD")"
  python3 - "$REL/preseed.cfg" "$NODE_IP" "$PORT" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1])
host=sys.argv[2]
port=sys.argv[3]
lines=p.read_text(encoding="utf-8").splitlines()
out=[]
late=(
    "d-i preseed/late_command string "
    f"in-target /usr/bin/curl -fsSL http://{host}:{port}/veyra/v0.9.2/veyra-payload.tar.gz -o /root/veyra-payload.tar.gz; "
    "in-target /bin/tar -xzf /root/veyra-payload.tar.gz -C /root; "
    "in-target /bin/bash -c 'cd /root/veyra && chmod +x scripts/*.sh && ./scripts/install-debian.sh'; "
    "in-target grub-install --target=x86_64-efi --efi-directory=/boot/efi --bootloader-id=Veyra --removable --no-nvram --recheck; "
    "in-target update-grub; "
    "in-target rm -rf /root/veyra /root/veyra-payload.tar.gz"
)
have_fw_pkg=False
have_fw_enable=False
for line in lines:
    if line.startswith("d-i preseed/late_command string "):
        out.append(late)
    elif line.startswith("d-i pkgsel/include string"):
        if "firmware-realtek" not in line.split():
            line += " firmware-realtek"
        have_fw_pkg=True
        out.append(line.replace("10.10.10.236", host))
    elif line.startswith("d-i apt-setup/non-free-firmware boolean"):
        out.append("d-i apt-setup/non-free-firmware boolean true")
        have_fw_enable=True
    else:
        out.append(line.replace("10.10.10.236", host))
if not have_fw_enable:
    out.append("d-i apt-setup/non-free-firmware boolean true")
if not have_fw_pkg:
    out.append("d-i pkgsel/include string firmware-realtek")
out.append("d-i hw-detect/load_firmware boolean true")
p.write_text("\n".join(out)+"\n", encoding="utf-8")
PY
  grep -Fq "http://$NODE_IP:$PORT/veyra/v0.9.2/veyra-payload.tar.gz" "$REL/preseed.cfg"
  ! grep -Fq "/cdrom/veyra" "$REL/preseed.cfg"
fi

{
  echo '#!ipxe'
  echo "set server $NODE_IP"
  echo 'set base http://${server}:8098/veyra/v0.9.2'
  echo 'menu Veyra Network Deployment'
  echo 'item --key v veyra092 Veyra v0.9.2 Auto Install (DESTRUCTIVE)'
  echo 'item --key s shell Safe iPXE shell / PXE test'
  echo 'choose --default shell --timeout 10000 target && goto ${target}'
  echo ':veyra092'
  echo 'echo Booting signed Veyra v0.9.2 from Node C...'
  echo 'echo Starting original Veyra v0.9.2 Debian installer directly'
  echo 'ifstat'
  echo 'route'
  echo 'dhcp || goto netfail'
  echo 'route'
  echo 'imgfree autoexec.ipxe ||'
  echo 'kernel ${base}/vmlinuz initrd=initrd.magic auto=true priority=critical netcfg/choose_interface=auto url=${base}/preseed.cfg --- || goto bootfail'
  echo 'initrd --name initrd.gz ${base}/initrd.gz || goto bootfail'
  echo 'imgstat'
  echo 'boot || goto bootfail'
  echo ':installer'
  echo 'goto bootfail'
  echo ':netfail'
  echo 'echo Veyra network refresh FAILED - remaining in iPXE for diagnostics.'
  echo 'ifstat'
  echo 'route'
  echo 'shell'
  echo ':bootfail'
  echo 'echo Veyra installer handoff FAILED - remaining in iPXE for diagnostics.'
  echo 'imgstat'
  echo 'shell'
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
dhcp-range=10.10.0.0,proxy,255.255.0.0
dhcp-mac=set:veyra,$VEYRA_MAC
dhcp-ignore=tag:!veyra
dhcp-userclass=set:ipxe,iPXE
dhcp-match=set:efi64,option:client-arch,7
dhcp-match=set:efi64,option:client-arch,9
pxe-service=tag:veyra,tag:efi64,x86-64_EFI,"Veyra UEFI Network Install",snponly.efi,$NODE_IP
pxe-service=tag:veyra,tag:!efi64,x86PC,"Veyra BIOS Network Install",undionly.kpxe,$NODE_IP
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
ss -lun | grep -q ':4011 '
ss -lnt | grep -q ':8098 '

curl -fsS "http://127.0.0.1:$PORT/autoexec.ipxe" >/dev/null
curl -fsS "http://127.0.0.1:$PORT/veyra/v0.9.2/preseed.cfg" | grep -Fq "veyra-payload.tar.gz"
curl -fsSI "http://127.0.0.1:$PORT/veyra/v0.9.2/veyra-payload.tar.gz" >/dev/null
curl -fsS "http://127.0.0.1:$PORT/veyra/v0.9.2/Veyra-AutoInstall-v0.9.2.sha256" | grep -q "$EXPECTED"
curl -fsSI "http://127.0.0.1:$PORT/veyra/v0.9.2/Veyra-AutoInstall-v0.9.2.iso" >/dev/null

if command -v tftp >/dev/null 2>&1; then
  tmp="$(mktemp -d)"
  (cd "$tmp" && timeout 8 tftp 127.0.0.1 -m binary -c get snponly.efi >/dev/null 2>&1)
  cmp -s "$tmp/snponly.efi" "$TFTP/snponly.efi"
  rm -rf "$tmp"
fi

grep -Fq 'kernel ${base}/vmlinuz initrd=initrd.magic' "$HTTP/autoexec.ipxe"
grep -Fq 'initrd --name initrd.gz ${base}/initrd.gz' "$HTTP/autoexec.ipxe"
! grep -Fq 'sanboot ' "$HTTP/autoexec.ipxe"
! grep -Eq 'debian-installer/amd64|initrd-generic.gz' "$HTTP/autoexec.ipxe"
cmp -s "$REL/vmlinuz" "$REL/vmlinuz-cd"
cmp -s "$REL/initrd.gz" "$REL/initrd-cd.gz"
echo "=== PXE READY ==="
echo "TFTP server: $NODE_IP:69"
echo "UEFI bootfile: snponly.efi"
echo "BIOS bootfile: undionly.kpxe"
echo "iPXE script: http://$NODE_IP:$PORT/autoexec.ipxe"
echo "ISO: http://$NODE_IP:$PORT/veyra/v0.9.2/Veyra-AutoInstall-v0.9.2.iso"
echo "sha256=$EXPECTED"
echo "kernel_fallback=$kernel_ok initrd_fallback=$initrd_ok preseed=$preseed_ok"
echo "ProxyDHCP target MAC: $VEYRA_MAC"
echo "VEYRA_DIRECT_ISO_KERNEL_PUBLISHED_FOR_HARDWARE_TEST"
