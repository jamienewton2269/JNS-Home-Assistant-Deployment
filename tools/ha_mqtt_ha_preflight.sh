#!/usr/bin/env bash
# Redundancy preflight — read-only. No service changes, no secrets collected.
set -u
export LC_ALL=C
PATH=/usr/sbin:/usr/bin:/sbin:/bin
run() {
  printf '\n=== %s ===\n' "$1"
  shift
  timeout 15 "$@" 2>&1 || echo "WARN: check failed/expired ($?)"
}
echo "HA / MQTT HIGH AVAILABILITY PRE-FLIGHT (READ ONLY)"
date -Is
hostname -f 2>/dev/null || hostname
run "Host addresses (audit only; do not use addresses in service configs)" ip -brief address
run "Cluster state" pvecm status
run "Corosync configuration existence" test -f /etc/pve/corosync.conf
run "Storage status" pvesm status
run "Replication status" pvesr status
run "VM inventory" qm list
run "LXC inventory" pct list
run "Local VM 905 configuration (if present)" qm config 905
run "Local CT 212 configuration (if present)" pct config 212
run "Local CT 214 configuration (if present)" pct config 214
run "Thin pool capacity" lvs --units g -o vg_name,lv_name,lv_size,data_percent,metadata_percent
run "Filesystem capacity" df -hT
for host in nodea nodeb nodec ha-general.home.arpa mqtt.home.arpa; do
  run "DNS $host" getent ahostsv4 "$host"
done
for host in nodea nodeb; do
  echo
  echo "=== Remote host $host (DNS-first / batch SSH, non-interactive) ==="
  if ! getent hosts "$host" >/dev/null; then
    echo "BLOCKED: hostname cannot resolve; no literal-IP fallback"
    continue
  fi
  timeout 24 ssh -o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=yes "$host" \
    'hostname; pvecm status 2>&1 | head -14; qm list; pct list; pvesm status; pvesr status 2>&1' \
    2>&1 || echo "WARN: remote audit failed; no changes made"
done
echo
echo "=== END: read-only. No takeover, backup, cluster join or restart performed ==="
