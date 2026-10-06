#!/usr/bin/env bash
set -euo pipefail
echo "=== DISCOVER HA-GENERAL / BLUETOOTH / CLOCK ==="
date -Is
echo "runner=$(hostname)"
for H in nodea nodeb; do
  echo
  echo "===== $H ====="
  timeout 15s ssh -o BatchMode=yes "$H" '
    echo "-- host/ip --"; hostname; ip -br -4 addr || true
    echo "-- qm list --"; qm list || true
    echo "-- pct list --"; pct list || true
    echo "-- names bluetooth/audio/ha --";
    (grep -RHiE "^(name|hostname):.*(bluetooth|audio|ha-general|general)" /etc/pve/qemu-server /etc/pve/lxc 2>/dev/null || true)
  '
done
echo
echo "===== HA900 / OLD CLOCK SEARCH VIA NODE A ====="
timeout 20s ssh -o BatchMode=yes nodea '
  for id in 900 901 902 903 904 905; do
    qm status "$id" >/dev/null 2>&1 || continue
    echo "VM $id $(qm config "$id" 2>/dev/null | grep -E "^(name|ipconfig0|net0):" || true)"
  done
'
echo
echo "===== ROUTE/ARP RELEVANT ====="
timeout 15s ssh -o BatchMode=yes nodea 'ip neigh | sort | tail -n 80 || true'
