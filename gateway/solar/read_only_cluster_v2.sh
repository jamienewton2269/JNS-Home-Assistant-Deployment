#!/usr/bin/env bash
# JNS Solar Economy read-only feasibility: cluster boundaries, duplicate IDs,
# and whether the Node C runner can inspect its local Proxmox host.
set -Eeuo pipefail
export LC_ALL=C
echo "JNS_SOLAR_CLUSTER_AUDIT=2"
echo "=== NODE C LOCAL NONPRIVILEGED INSPECTION ==="
echo "RUNNER_HOST=$(hostname -s)"
id -un
for command in "pvecm nodes" "pvecm status" "qm list" "pct list" "pvesm status" "free -m"; do
  echo "-- local command: $command --"
  timeout 12 bash -c "$command" 2>&1 | head -26 || echo "LOCAL_COMMAND_NOT_PERMITTED_OR_UNAVAILABLE"
done
echo "-- nodec top-level guest configuration IDs, if readable --"
for p in /etc/pve/nodes/nodec/qemu-server /etc/pve/nodes/nodec/lxc; do
  if test -r "$p"; then
    find "$p" -maxdepth 1 -name '*.conf' -printf '%f\n' 2>/dev/null | sort -V | head -35
  else
    echo "NOT_READABLE $p"
  fi
done
for target in nodea nodeb; do
  echo "=== TRUSTED HOST $target CLUSTER AND RESOURCE OWNERSHIP ==="
  if ! timeout 12 ssh -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=5 "$target" 'test "$(id -u)" = 0' >/dev/null 2>&1; then
    echo "UNREACHABLE_OR_NOT_ROOT $target"
    continue
  fi
  timeout 90 ssh -o BatchMode=yes -o StrictHostKeyChecking=yes "$target" 'bash -s' <<'REMOTE_AUDIT' || echo "REMOTE_PARTIAL_FAILURE"
set -u
echo "HOST=$(hostname -s)"
echo "-- cluster members --"
pvecm nodes 2>&1 | head -24 || :
echo "-- cluster quorum --"
pvecm status 2>&1 | head -36 || :
echo "-- cluster guest scope (id / node / name / status / mem / maxmem) --"
pvesh get /cluster/resources --type vm --output-format json 2>/dev/null |
 python3 -c 'import json,sys
try:
 for d in sorted(json.load(sys.stdin),key=lambda v:(v.get("node",""),v.get("vmid",0))):
  print(d.get("vmid"),d.get("node"),d.get("name"),d.get("status"),d.get("mem"),d.get("maxmem"))
except Exception:print("CLUSTER_RESOURCE_LIST_UNAVAILABLE")' || :
echo "-- host effective memory --"
free -m | head -3 || :
echo "-- local network storage mount endpoints: names only --"
for path in /mnt/jns-dns-master /mnt/jns-dns-live /mnt/pve/NAS /mnt/pve/WD-BACKUP; do
  echo "MOUNT_CHECK=$path"
  findmnt -rn -T "$path" -o TARGET,FSTYPE 2>/dev/null | head -1 || :
done
echo "-- direct host service files required if other node sleeps --"
for x in /etc/systemd/system/natural-automation.service /etc/systemd/system/jns-infrastructure-discovery.service /etc/systemd/system/jns-management-bridge.service /etc/systemd/system/jns-dns-reservation-importer.service; do
  if test -e "$x"; then
    echo "SERVICE_FILE=$(basename "$x")"
  fi
done
REMOTE_AUDIT
done
echo "JNS_SOLAR_CLUSTER_AUDIT_COMPLETE_READ_ONLY"
