#!/usr/bin/env bash
set -euo pipefail
echo "=== HA CLUSTER READ-ONLY RESOURCE / REPLICA AUDIT ==="
date -Is

for host in nodea nodeb; do
  echo
  echo "################################################################"
  echo "### HOST: $host"
  echo "################################################################"
  ssh -o BatchMode=yes -o ConnectTimeout=10 "$host" 'bash -s' <<'REMOTE'
set -u
echo "--- IDENTITY / LOAD ---"
hostname
uptime
echo
echo "--- MEMORY ---"
free -h
echo
echo "--- ROOT / PVE STORAGE ---"
df -hT / /var/lib/vz 2>/dev/null || df -hT /
echo
echo "--- PVE STORAGE STATUS ---"
pvesm status 2>&1 || true
echo
echo "--- QEMU VMS ---"
qm list 2>&1 || true
echo
echo "--- LXC CONTAINERS ---"
pct list 2>&1 || true
echo
echo "--- QEMU LIVE RESOURCE DATA ---"
NODE=$(hostname)
pvesh get "/nodes/$NODE/qemu" --output-format json-pretty 2>&1 || true
echo
echo "--- LXC LIVE RESOURCE DATA ---"
pvesh get "/nodes/$NODE/lxc" --output-format json-pretty 2>&1 || true
echo
echo "--- HA / GUARDIAN / REPLICATION-RELATED UNITS ---"
systemctl list-units --all --no-pager 2>/dev/null | grep -Ei 'guardian|replic|sync|home.?assistant|ha[-_]?sync|jns' | head -200 || true
echo
echo "--- REPLICATION CONFIG ---"
cat /etc/pve/replication.cfg 2>&1 || true
echo
echo "--- CLUSTER REPLICATION STATUS ---"
pvesh get /cluster/replication --output-format json-pretty 2>&1 || true
echo
echo "--- SELECTED VM CONFIGS (if present) ---"
for id in 900 901 902 903 904 905 906 907 908 909; do
  if qm status "$id" >/dev/null 2>&1; then
    echo "### VM $id"
    qm status "$id" --verbose 2>&1 || qm status "$id" 2>&1 || true
    qm config "$id" 2>&1 | grep -E '^(name|memory|balloon|cores|sockets|net[0-9]+|scsi[0-9]+|virtio[0-9]+|ide[0-9]+|boot|onboot|startup|tags):' || true
  fi
done
echo
echo "--- RECENT BACKUP / SYNC ARTIFACTS ---"
find /var/lib/vz/dump /var/lib/vz/snippets /etc/pve -maxdepth 3 -type f \( -iname '*900*' -o -iname '*901*' -o -iname '*902*' -o -iname '*sync*' -o -iname '*replic*' -o -iname '*guardian*' \) -printf '%TY-%Tm-%Td %TH:%TM:%TS %10s %p\n' 2>/dev/null | sort -r | head -100 || true
REMOTE
done

echo
echo "=== END AUDIT ==="
