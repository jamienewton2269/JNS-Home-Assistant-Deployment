#!/usr/bin/env bash
# JNS Steward replication preflight v0.1 — strictly READ ONLY.
set -u
export LC_ALL=C
echo "JNS REPLICATION PREFLIGHT $(date -Is) host=$(hostname)"
for cmd in "hostname -f" "pvecm status" "pvesm status" "pvesr status" "zpool list" "zfs list -t filesystem,volume -o name,used,available,refer,mountpoint" "df -h /" "lvs -a -o vg_name,lv_name,lv_size,data_percent,origin"; do
 echo; echo "=== $cmd ==="; timeout 15 bash -c "$cmd" 2>&1 || echo "CHECK UNAVAILABLE"; done
for id in 902 905 906; do
 echo; echo "=== VM $id ==="
 qm status "$id" 2>&1 || true
 qm config "$id" 2>&1 | grep -E '^(name|memory|cores|sockets|bios|boot|scsi|virtio|sata|ide|efidisk|tpmstate|net|onboot|startup|agent|unused|lock):?' || true
 qm listsnapshot "$id" 2>&1 | head -40 || true
done
for id in 212 214 210; do
 echo; echo "=== CT $id ==="
 pct status "$id" 2>&1 || true
 pct config "$id" 2>&1 | grep -E '^(hostname|rootfs|mp[0-9]|net[0-9]|onboot|features|unprivileged|lxc.mount.entry):?' || true
done
echo; echo "=== HOST DNS ==="
for host in nodea nodeb ha-primary.home.arpa ha-general.home.arpa ha-security.home.arpa mqtt.home.arpa;do getent hosts "$host" || echo "UNRESOLVED: $host";done
echo; echo "NO MODIFICATIONS PERFORMED"
