#!/usr/bin/env bash
set -u
echo "=== HA FAILOVER PREREQUISITE AUDIT ==="
date -Is
for host in nodea nodeb; do
  echo
  echo "################################################################"
  echo "### $host"
  echo "################################################################"
  timeout 90s ssh -o BatchMode=yes -o ConnectTimeout=10 "$host" 'bash -s' <<'REMOTE'
set -u
run(){ label="$1"; shift; echo; echo "--- $label ---"; timeout 15s "$@" 2>&1 || echo "[WARN/TIMEOUT] $label rc=$?"; }
runs(){ label="$1"; cmd="$2"; echo; echo "--- $label ---"; timeout 20s bash -lc "$cmd" 2>&1 || echo "[WARN/TIMEOUT] $label rc=$?"; }

run "HOSTNAME" hostname
run "PVE VERSION" pveversion
run "CLUSTER STATUS" pvecm status
run "CLUSTER NODES" pvecm nodes
run "REPLICATION STATUS" pvesr status
runs "REPLICATION CONFIG" 'cat /etc/pve/replication.cfg 2>/dev/null || true'
run "STORAGE STATUS" pvesm status
runs "ZFS DATASETS" 'zfs list -o name,used,avail,refer,mountpoint 2>/dev/null || true'
runs "ZFS POOLS" 'zpool status 2>/dev/null || true'
runs "VM LIST" 'qm list'
runs "HA VM DISK CONFIGS" 'for id in 902 903 905; do echo "### VM $id"; qm config "$id" 2>/dev/null | grep -E "^(name|memory|balloon|cores|net0|scsi0|efidisk0|onboot|startup|tags):" || echo MISSING; done'
runs "JNS FAILOVER / SYNC FILES" 'find /etc/systemd/system /usr/local /opt /root /var/lib -maxdepth 4 -type f 2>/dev/null | grep -Ei "jns.*(sync|guardian|failover|replica|promot)|ha.*(sync|guardian|failover|replica|promot)" | head -250 || true'
runs "JNS RELATED UNIT FILES" 'systemctl list-unit-files --no-pager 2>/dev/null | grep -Ei "jns.*(sync|guardian|failover|replica|promot)|ha.*(sync|guardian|failover|replica|promot)" | head -200 || true'
runs "GUARDIAN CONTAINER CONFIG" 'for id in 115 116 117; do pct status "$id" >/dev/null 2>&1 && { echo "### CT$id"; pct config "$id"; }; done'
REMOTE
done
echo
echo "=== END PREREQUISITE AUDIT ==="
