#!/usr/bin/env bash
# JNS guest-purpose audit v1. Read-only. No guest starts, modifications, or restarts.
set -u
echo "JNS GUEST AUDIT $(date -Is) host=$(hostname -s)"
echo "=== GUEST SUMMARY ==="
qm list
pct list
echo "=== HOST MEMORY ==="
free -h
echo "=== QEMU CONFIGURATIONS ==="
while read -r id _; do
 [[ "$id" =~ ^[0-9]+$ ]] || continue
 echo "--- VM $id ---"
 qm status "$id" 2>&1
 qm config "$id" 2>&1 | grep -E '^(name|memory|cores|onboot|boot|agent|net[0-9]|scsi[0-9]|virtio[0-9]|sata[0-9]|ide[0-9]|efidisk[0-9]|unused[0-9]|description|tags):' || true
done < <(qm list | tail -n +2)
echo "=== LXC CONFIGURATIONS ==="
while read -r id _; do
 [[ "$id" =~ ^[0-9]+$ ]] || continue
 echo "--- CT $id ---"
 pct status "$id" 2>&1
 pct config "$id" 2>&1 | grep -E '^(hostname|memory|swap|cores|onboot|net[0-9]|rootfs|mp[0-9]|description|tags):' || true
done < <(pct list | tail -n +2)
echo "=== RUNNING LXC SERVICE IDENTIFICATION ==="
while read -r id status rest; do
 [[ "$id" =~ ^[0-9]+$ && "$status" == running ]] || continue
 echo "--- CT $id ---"
 timeout 12 pct exec "$id" -- sh -c '
echo "HOST: $(hostname)"
echo "SERVICES:"
systemctl --no-pager --no-legend --type=service --state=running 2>/dev/null | head -60 || true
echo "LISTENING SOCKETS:"
ss -lntup 2>/dev/null | head -45 || true
echo "TOP COMMANDS:"
ps -eo comm --sort=comm 2>/dev/null | uniq -c | sort -nr | head -20 || true
' 2>&1 || echo "Container introspection timed out / unavailable"
done < <(pct list | tail -n +2)
echo "=== END READ-ONLY AUDIT ==="
