#!/usr/bin/env bash
set -euo pipefail

VMID="${1:-909}"
MOUNTPOINT="/mnt/ha909-ro"
NBD="/dev/nbd7"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root on the Proxmox host." >&2
  exit 1
fi

echo "=== VM $VMID PRECHECK ==="
qm status "$VMID" || exit 1
qm config "$VMID" | sed -n '1,80p'

status="$(qm status "$VMID" | awk '{print $2}')"
if [[ "$status" == "running" ]]; then
  echo
  echo "Gracefully shutting down VM $VMID..."
  qm shutdown "$VMID" --timeout 90 || true
  for _ in $(seq 1 30); do
    [[ "$(qm status "$VMID" | awk '{print $2}')" == "stopped" ]] && break
    sleep 2
  done
fi

if [[ "$(qm status "$VMID" | awk '{print $2}')" != "stopped" ]]; then
  echo "VM $VMID did not stop cleanly; refusing to attach its disk." >&2
  exit 2
fi

echo
echo "=== VM $VMID STOPPED ==="
qm status "$VMID"

VOLID="$(qm config "$VMID" | awk -F': ' '/^scsi0:/{print $2}' | cut -d, -f1)"
if [[ -z "$VOLID" ]]; then
  echo "Could not determine scsi0 volume." >&2
  exit 3
fi
DISK="$(pvesm path "$VOLID")"
echo "Disk volume: $VOLID"
echo "Disk path:   $DISK"

cleanup() {
  set +e
  umount "$MOUNTPOINT" 2>/dev/null || true
  qemu-nbd --disconnect "$NBD" 2>/dev/null || true
}
trap cleanup EXIT

command -v qemu-nbd >/dev/null || {
  echo "qemu-nbd is not installed; install package qemu-utils and retry." >&2
  exit 4
}

modprobe nbd max_part=16
qemu-nbd --read-only --connect="$NBD" "$DISK"
udevadm settle || true
sleep 2

echo
echo "=== PARTITIONS ==="
lsblk -o NAME,SIZE,FSTYPE,LABEL,PARTLABEL,UUID,MOUNTPOINTS "$NBD"

DATA_PART="$(lsblk -rno PATH,LABEL "$NBD" | awk '$2=="hassos-data"{print $1; exit}')"
if [[ -z "$DATA_PART" ]]; then
  DATA_PART="$(blkid | awk -F: '/LABEL="hassos-data"/ && /\/dev\/nbd7p/{print $1; exit}')"
fi
if [[ -z "$DATA_PART" ]]; then
  echo "Could not locate hassos-data partition; leaving disk untouched." >&2
  exit 5
fi

mkdir -p "$MOUNTPOINT"
mount -o ro,noload "$DATA_PART" "$MOUNTPOINT" 2>/dev/null || mount -o ro "$DATA_PART" "$MOUNTPOINT"

echo
echo "=== HAOS DATA ROOT ==="
find "$MOUNTPOINT" -maxdepth 2 -mindepth 1 -printf '%y %p\n' 2>/dev/null | head -120

echo
echo "=== HOME ASSISTANT BACKUP CANDIDATES ==="
find "$MOUNTPOINT" -type f \( -name '*.tar' -o -name '*.tar.gz' -o -name '*.tar.zst' -o -name '*.backup' \) \
  -printf '%TY-%Tm-%Td %TH:%TM %s %p\n' 2>/dev/null | sort -r | head -100

echo
echo "=== HOME ASSISTANT CONFIG CANDIDATES ==="
find "$MOUNTPOINT" -type f \( \
  -name 'configuration.yaml' -o \
  -name 'automations.yaml' -o \
  -name 'scripts.yaml' -o \
  -name 'core.config_entries' -o \
  -name 'core.device_registry' -o \
  -name 'core.entity_registry' -o \
  -name 'zigbee.db' -o \
  -name 'database.db' -o \
  -name 'configuration.yaml' \
\) -printf '%TY-%Tm-%Td %TH:%TM %s %p\n' 2>/dev/null | sort -r | head -160

echo
echo "=== LIKELY HA CONFIG DIRECTORIES ==="
find "$MOUNTPOINT" -type d \( -path '*/homeassistant' -o -path '*/home-assistant' -o -path '*/config' -o -path '*/backup' -o -path '*/backups' \) \
  -printf '%p\n' 2>/dev/null | head -100

echo
echo "Inspection complete. VM $VMID remains STOPPED; disk was mounted read-only only."
