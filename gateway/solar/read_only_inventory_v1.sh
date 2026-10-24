#!/usr/bin/env bash
# JNS solar economy feasibility audit v1. READ ONLY. No migrations, shutdowns,
# storage mounts, system changes, keys, IP addresses, credentials or HA states.
set -Eeuo pipefail
export LC_ALL=C
echo "JNS_SOLAR_AUDIT_VERSION=1"
date -u +"AUDIT_UTC=%Y-%m-%dT%H:%M:%SZ"
echo "RUNNER_HOST=$(hostname -s)"
echo "=== TRUSTED PROXMOX NODE INVENTORY ==="
for target in nodea nodeb nodec; do
  echo "=== TARGET $target ==="
  if ! timeout 12 ssh -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=5 "$target" 'command -v qm >/dev/null && test "$(id -u)" = 0' >/dev/null 2>&1; then
    echo "TARGET_UNAVAILABLE_OR_NOT_PVE_ROOT=$target"
    continue
  fi
  timeout 90 ssh -o BatchMode=yes -o StrictHostKeyChecking=yes "$target" 'bash -s' <<'REMOTE_AUDIT' || echo "TARGET_AUDIT_FAILED"
set -u
echo "HOST=$(hostname -s)"
printf 'CPUS='; nproc 2>/dev/null || :
awk '/MemTotal:/ {print "RAM_KIB="$2}' /proc/meminfo
printf 'UPTIME='; uptime -p 2>/dev/null || :
echo '-- LOCAL VM LIST: id status memoryMB name --'
qm list 2>/dev/null | awk 'NR>1{print $1, $3, $4, $2}' || :
echo '-- LOCAL CT LIST: id status name --'
pct list 2>/dev/null | awk 'NR>1{print $1, $2, $3}' || :
echo '-- SAFE VM RESOURCE CONFIGS --'
for id in $(qm list 2>/dev/null | awk 'NR>1&&$1~/^[0-9]+$/{print $1}'); do
  echo "VM_ID=$id"
  qm config "$id" 2>/dev/null | grep -E '^(name|cores|sockets|memory|balloon|onboot|startup|scsi[0-9]+|virtio[0-9]+|sata[0-9]+|ide[0-9]+|efidisk[0-9]+|hostpci[0-9]+|usb[0-9]+):' | head -24 || :
done
echo '-- SAFE CT RESOURCE CONFIGS --'
for id in $(pct list 2>/dev/null | awk 'NR>1&&$1~/^[0-9]+$/{print $1}'); do
  echo "CT_ID=$id"
  pct config "$id" 2>/dev/null | grep -E '^(hostname|cores|memory|swap|onboot|startup|rootfs|mp[0-9]+|unprivileged):' | head -20 || :
done
echo '-- STORAGE CAPACITY / STATE --'
pvesm status 2>/dev/null | head -25 || :
echo '-- ZFS CAPACITY (if relevant) --'
if command -v zpool >/dev/null 2>&1; then zpool list -H -o name,size,alloc,free,health 2>/dev/null | head -12 || :; fi
echo '-- NETWORK-MOUNT DEPENDENCIES (mountpoints and types only) --'
findmnt -rn -t nfs,nfs4,cifs -o TARGET,FSTYPE 2>/dev/null | head -15 || :
echo '-- CLUSTER MEMBERS / QUORUM --'
pvecm status 2>/dev/null | grep -E '^(Cluster Name:|Nodes:|Quorate:|Node ID:|Ring ID:|Expected votes:|Total votes:|Quorum:)' | head -15 || :
echo '-- HA RESOURCE STATE --'
if command -v ha-manager >/dev/null 2>&1; then ha-manager status 2>/dev/null | grep -E '^(quorum|master|lrm|service)' | head -35 || :; fi
echo '-- BACKUP JOB TARGETS (no personal details) --'
if command -v pvesh >/dev/null 2>&1; then
  pvesh get /cluster/backup --output-format json 2>/dev/null |
    python3 -c 'import json,sys
try:
 data=json.load(sys.stdin)
 for x in data:
  print("BACKUP",x.get("id"),"storage",x.get("storage"),"schedule",x.get("schedule"),"enabled",x.get("enabled",1))
except Exception:
 print("BACKUP_JOB_METADATA_UNAVAILABLE")' || :
fi
echo '-- RELEVANT HOST SERVICES (names only) --'
systemctl list-units --type=service --state=running --no-legend --no-pager 2>/dev/null |
 awk '{print $1}' | grep -Ei 'jns|steward|natural|guardian|lunar|sheriff|dnsmasq|mosquitto|backup|pve|corosync|runner' | head -35 || :
REMOTE_AUDIT
done
echo "=== LOCAL RUNNER SERVICES ==="
systemctl list-units --type=service --state=running --no-legend --no-pager 2>/dev/null |
  awk '{print $1}' | grep -Ei 'jns|steward|natural|github|runner|pve' | head -25 || :
echo "JNS_SOLAR_AUDIT_COMPLETE_READ_ONLY"
