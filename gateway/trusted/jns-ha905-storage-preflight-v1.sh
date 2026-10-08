#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
OUT=/opt/jns-ha-control-plane/reports
mkdir -p "$OUT"
REPORT="$OUT/ha905-control-audit-$(date +%Y%m%dT%H%M%S).txt"
ssh_runner() { /usr/sbin/runuser -u github-runner -- ssh -o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=yes -o HostName=10.10.10.235 nodeb "$@"; }
{
echo "=== HA905 STORAGE / DASHBOARD AUDIT: $(date -Is) ==="
echo "=== VM STATUS ==="
ssh_runner 'qm status 905'
echo "=== READ-ONLY HAOS GUEST INSPECTION ==="
# Proxmox QEMU guest agent exec; no Home Assistant API token required.
ssh_runner 'qm guest exec 905 -- /bin/sh -c '"'"'echo GUEST_AGENT_OK; ls -ld /mnt/data/supervisor/homeassistant/.storage /mnt/data/supervisor/homeassistant/packages 2>&1; ls /mnt/data/supervisor/homeassistant/.storage 2>/dev/null | grep -E "^(lovelace|core.entity_registry|core.device_registry|core.config_entries)" | head -60; echo "=== DASHBOARD CONFIG FILES ==="; ls /mnt/data/supervisor/homeassistant/*dashboard* /mnt/data/supervisor/homeassistant/*lovelace* 2>/dev/null || true'"'"''
echo "=== END ==="
} 2>&1 | tee "$REPORT"
echo "Report written: $REPORT"
echo "No device control or configuration changes made."
