#!/usr/bin/env bash
set -euo pipefail
echo "=== INSPECT AUDIO VMS AND HA-GENERAL ==="
date -Is
for X in "nodea 214" "nodeb 219" "nodeb 905"; do
  set -- $X; H=$1; ID=$2
  echo; echo "===== $H VM $ID ====="
  timeout 15s ssh -o BatchMode=yes "$H" "
    qm config $ID || true
    echo -- guest-agent-net --
    qm guest cmd $ID network-get-interfaces 2>&1 || true
    echo -- guest-agent-os --
    qm guest cmd $ID get-osinfo 2>&1 || true
  "
done
echo; echo "===== AUDIO SERVICE CHECK ====="
for X in "nodea 214" "nodeb 219"; do
 set -- $X; H=$1; ID=$2
 echo "-- $H/$ID --"
 timeout 15s ssh -o BatchMode=yes "$H" "qm guest exec $ID -- bash -lc 'hostname; ip -br -4 a; systemctl --no-pager --type=service --state=running | grep -Ei "blue|pulse|pipe|audio|speaker" || true; bluetoothctl devices Connected 2>/dev/null || true' 2>&1 || true"
done
