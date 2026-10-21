#!/usr/bin/env bash
# JNS Steward A/B replica transport pilot v0.1. DRY RUN ONLY.
# No SSH trust changes, snapshots, receives, VM registration, start or deletion.
set -euo pipefail
usage(){ echo "Usage: $0 nodea|nodeb"; exit 2; }
[[ $# == 1 ]] || usage
case "$1" in nodea) peer=nodeb;; nodeb) peer=nodea;; *) usage;; esac
printf 'LOCAL=%s PEER=%s\n' "$(hostname -s)" "$peer"
if [[ "$(hostname -s)" != "$1" ]]; then echo "Wrong local host; refusing"; exit 2; fi
if ! getent ahosts "$peer" >/dev/null; then
 echo "BLOCKED: peer $peer unresolved. Correct DNS first; do not hardcode IP addresses."
 exit 3
fi
echo "== Local prerequisites =="
command -v zfs;command -v zpool;command -v ssh
zpool status vmdata
zfs list -H -o name,used,avail,refer vmdata
echo "== Readonly source candidates =="
if [[ "$1" == nodea ]]; then vmid=902; else vmid=905; fi
qm status "$vmid"
qm config "$vmid" | grep -E '^(name|scsi0|efidisk0|net0|bios|onboot):'
zfs list -H -o name,used,refer "vmdata/vm-${vmid}-disk-1"
echo "== Peer availability (strict SSH identity) =="
timeout 12 ssh -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=5 "$peer" \
 'hostname -s; zpool status vmdata; zfs list -H -o name,used,avail vmdata; qm list' || {
  echo 'BLOCKED: trusted SSH / peer readiness not established';exit 4;
 }
echo "== Pilot proposal =="
echo "Source: vmdata/vm-${vmid}-disk-1 on $1"
echo "Destination: isolated, unregistered dataset on $peer (name to be approved after disk inventory)"
echo "Application consistency and HA service freeze/export strategy REQUIRED before snapshot-based recovery claim."
echo "No dataset created. No data sent. No VM changed. No automated promotion."
