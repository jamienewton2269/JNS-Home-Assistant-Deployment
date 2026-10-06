#!/usr/bin/env bash
set -u

echo "=== HA CLUSTER READ-ONLY RESOURCE / REPLICA AUDIT ==="
date -Is

run_host() {
  host="$1"
  echo
  echo "################################################################"
  echo "### HOST: $host"
  echo "################################################################"

  timeout 120s ssh -o BatchMode=yes -o ConnectTimeout=10 -o ServerAliveInterval=10 -o ServerAliveCountMax=2 "$host" 'bash -s' <<'REMOTE'
set -u

safe() {
  label="$1"; secs="$2"; shift 2
  echo
  echo "--- $label ---"
  timeout --signal=TERM --kill-after=3s "$secs"s "$@" 2>&1
  rc=$?
  if [ "$rc" -eq 124 ] || [ "$rc" -eq 137 ]; then
    echo "[TIMEOUT] $label exceeded $secs seconds"
  elif [ "$rc" -ne 0 ]; then
    echo "[WARN] $label exited rc=$rc"
  fi
  return 0
}

safe_shell() {
  label="$1"; secs="$2"; cmd="$3"
  echo
  echo "--- $label ---"
  timeout --signal=TERM --kill-after=3s "$secs"s bash -lc "$cmd" 2>&1
  rc=$?
  if [ "$rc" -eq 124 ] || [ "$rc" -eq 137 ]; then
    echo "[TIMEOUT] $label exceeded $secs seconds"
  elif [ "$rc" -ne 0 ]; then
    echo "[WARN] $label exited rc=$rc"
  fi
  return 0
}

safe_shell "IDENTITY / LOAD" 5 'hostname; uptime'
safe "MEMORY" 5 free -h
safe_shell "ROOT / PVE STORAGE" 8 'df -hT / /var/lib/vz 2>/dev/null || df -hT /'
safe "PVE STORAGE STATUS" 12 pvesm status
safe "QEMU VMS" 10 qm list
safe "LXC CONTAINERS" 10 pct list

NODE="$(hostname)"
safe "QEMU LIVE RESOURCE DATA" 15 pvesh get "/nodes/$NODE/qemu" --output-format json-pretty
safe "LXC LIVE RESOURCE DATA" 15 pvesh get "/nodes/$NODE/lxc" --output-format json-pretty

safe_shell "HA / GUARDIAN / REPLICATION-RELATED UNITS" 10   "systemctl list-units --all --no-pager 2>/dev/null | grep -Ei 'guardian|replic|sync|home.?assistant|ha[-_]?sync|jns' | head -200 || true"

safe_shell "REPLICATION CONFIG" 5 'cat /etc/pve/replication.cfg 2>/dev/null || true'
safe_shell "PVE REPLICATION STATUS" 15 'pvesr status 2>&1 || true'

echo
echo "--- SELECTED VM CONFIGS (if present) ---"
for id in 900 901 902 903 904 905 906 907 908 909; do
  if timeout 5s qm status "$id" >/dev/null 2>&1; then
    echo "### VM $id"
    timeout 5s qm status "$id" --verbose 2>&1 || timeout 5s qm status "$id" 2>&1 || echo "[WARN] VM $id status timed out/failed"
    timeout 8s qm config "$id" 2>&1 | grep -E '^(name|memory|balloon|cores|sockets|net[0-9]+|scsi[0-9]+|virtio[0-9]+|ide[0-9]+|boot|onboot|startup|tags):' || true
  fi
done

safe_shell "RECENT BACKUP / SYNC ARTIFACTS" 12   "find /var/lib/vz/dump /var/lib/vz/snippets /etc/pve -maxdepth 3 -type f \( -iname '*900*' -o -iname '*901*' -o -iname '*902*' -o -iname '*903*' -o -iname '*904*' -o -iname '*905*' -o -iname '*sync*' -o -iname '*replic*' -o -iname '*guardian*' \) -printf '%TY-%Tm-%Td %TH:%TM:%TS %10s %p\n' 2>/dev/null | sort -r | head -120 || true"

echo
echo "--- HOST AUDIT COMPLETE ---"
REMOTE

  rc=$?
  if [ "$rc" -eq 124 ]; then
    echo "[TIMEOUT] entire SSH audit for $host exceeded 120s; continuing to next host"
  elif [ "$rc" -ne 0 ]; then
    echo "[WARN] SSH audit for $host exited rc=$rc; continuing to next host"
  fi
}

run_host nodea
run_host nodeb

echo
echo "=== END AUDIT ==="
