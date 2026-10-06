#!/usr/bin/env bash
set -euo pipefail
echo "=== AUDIO PRECHANGE AUDIT V2 ==="
date -Is
echo "RANGE:"
for n in $(seq 220 240); do
 a=10.10.10.$n
 ping -c1 -W1 "$a" >/dev/null 2>&1 && s=UP || s=NO_REPLY
 echo "$a $s $(ip neigh show "$a" || true)"
done

echo "=== NODE A AUDIO ==="
ssh -o BatchMode=yes nodea "qm guest exec 214 -- /bin/bash -lc 'hostname; ip -br -4 a; ip route; echo NETPLAN; ls -la /etc/network/interfaces /etc/network/interfaces.d /etc/systemd/network /etc/NetworkManager/system-connections 2>/dev/null || true; echo BT; bluetoothctl devices 2>/dev/null || true; bluetoothctl info 73:81:7B:84:2A:AB 2>/dev/null || true; echo SERVICES; systemctl list-unit-files | grep -Ei \"bluetooth|audio|chime|clock|piper\" || true; echo FILES; find /opt /usr/local /etc/systemd/system /var/lib -maxdepth 3 -type f 2>/dev/null | grep -Ei \"audio|speaker|chime|clock|piper|westminster\" | head -100 || true'"

echo "=== NODE B AUDIO ==="
ssh -o BatchMode=yes nodeb "qm guest exec 219 -- /bin/bash -lc 'hostname; ip -br -4 a; ip route; echo NETPLAN; ls -la /etc/network/interfaces /etc/network/interfaces.d /etc/systemd/network /etc/NetworkManager/system-connections 2>/dev/null || true; echo BT; bluetoothctl devices 2>/dev/null || true; echo SERVICES; systemctl list-unit-files | grep -Ei \"bluetooth|audio|chime|clock|piper\" || true; echo FILES; find /opt /usr/local /etc/systemd/system /var/lib -maxdepth 3 -type f 2>/dev/null | grep -Ei \"audio|speaker|chime|clock|piper|westminster\" | head -100 || true'"

echo "=== DNS A ==="
ssh -o BatchMode=yes nodea "pct exec 217 -- sh -lc 'hostname; ip -br -4 a; find /opt /etc -maxdepth 4 -type f 2>/dev/null | grep -Ei \"AdGuardHome.yaml|rewrite\" | head -50; grep -RHi \"10.10.10.223\|ha-general\|rewrites:\" /opt /etc 2>/dev/null | head -100 || true'"
echo "=== DNS B ==="
ssh -o BatchMode=yes nodeb "pct exec 218 -- sh -lc 'hostname; ip -br -4 a; find /opt /etc -maxdepth 4 -type f 2>/dev/null | grep -Ei \"AdGuardHome.yaml|rewrite\" | head -50; grep -RHi \"10.10.10.223\|ha-general\|rewrites:\" /opt /etc 2>/dev/null | head -100 || true'"
