#!/usr/bin/env bash
set -euo pipefail
echo "=== AUDIO LIVE STATUS ==="
date -Is
ssh nodea "qm guest cmd 214 network-get-interfaces"
ssh nodeb "qm guest cmd 219 network-get-interfaces"
ssh nodea "qm guest exec 214 -- bluetoothctl info 73:81:7B:84:2A:AB"
