#!/usr/bin/env bash
set -euo pipefail
echo "=== STATIC AUDIO + DNS PREP ==="
date -Is
for X in "nodea 214" "nodeb 219"; do
 set -- $X; H=$1; ID=$2
 echo "===== $H/$ID network manager ====="
 ssh -o BatchMode=yes "$H" "qm guest exec $ID -- /bin/bash -lc 'echo NETPLAN; find /etc/netplan /etc/network /run/systemd/network -maxdepth 2 -type f -print -exec sed -n \"1,160p\" {} \\; 2>/dev/null || true; echo NETWORKCTL; networkctl status ens18 --no-pager 2>/dev/null || true; echo NMCLI; command -v nmcli >/dev/null && nmcli -f NAME,UUID,TYPE,DEVICE connection show || true; echo RESOLV; cat /etc/resolv.conf'"
done

echo "===== DNS REWRITES A ====="
ssh -o BatchMode=yes nodea "pct exec 217 -- sh -lc 'grep -n -A80 -B5 \"rewrites:\" /opt/AdGuardHome/AdGuardHome.yaml || true; echo FILTERS; grep -n -E \"ha-general|house-audio|10.10.10.22[0-9]\" /opt/AdGuardHome/AdGuardHome.yaml || true'"
echo "===== DNS REWRITES B ====="
ssh -o BatchMode=yes nodeb "pct exec 218 -- sh -lc 'grep -n -A80 -B5 \"rewrites:\" /opt/AdGuardHome/AdGuardHome.yaml || true; echo FILTERS; grep -n -E \"ha-general|house-audio|10.10.10.22[0-9]\" /opt/AdGuardHome/AdGuardHome.yaml || true'"

echo "===== HA905 SUPERVISOR / CONFIG ACCESS ====="
ssh -o BatchMode=yes nodeb "qm guest exec 905 -- /bin/bash -lc 'echo SHELL_OK; command -v ha || true; ha info 2>/dev/null || true; ls -ld /mnt/data/supervisor/homeassistant /config 2>/dev/null || true; find /mnt/data/supervisor/homeassistant -maxdepth 2 -type f 2>/dev/null | grep -Ei \"automation|script|configuration|media\" | head -80 || true'" || true
