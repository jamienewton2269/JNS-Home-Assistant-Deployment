#!/usr/bin/env bash
set -Eeuo pipefail
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=yes -o HostName=10.10.110.12 nodeb)
qga(){ "${SSH[@]}" "qm guest exec 905 -- /bin/sh -c $(printf '%q' "$1")"; }

echo "=== LIGHTING VIEW EXACT ==="
qga 'sed -n "630,730p" /mnt/data/supervisor/homeassistant/dashboards/testing.yaml'

echo "=== CLOCK SOUND HELPER SOURCE ==="
qga 'grep -Rli "general_clock_sound" /mnt/data/supervisor/homeassistant --exclude="*.db" --exclude="home-assistant.log*" 2>/dev/null | head -20'

echo "=== CLOCK SOUND HELPER DEFINITIONS ==="
qga 'grep -RnA12 -B4 "general_clock_sound" /mnt/data/supervisor/homeassistant/packages /mnt/data/supervisor/homeassistant/*.yaml /mnt/data/supervisor/homeassistant/jns 2>/dev/null | head -100'

echo "=== CURRENT LIVE LUX RESTORE ==="
qga 'grep -nE "sensor.0xa4c1383917c90309_(illuminance|outdoor_lux_10_minute_average)" /mnt/data/supervisor/homeassistant/.storage/core.restore_state | tail -20'
