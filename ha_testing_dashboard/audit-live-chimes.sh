#!/usr/bin/env bash
set -Eeuo pipefail
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=yes -o HostName=10.10.110.12 nodeb)
qga(){ "${SSH[@]}" "qm guest exec 905 -- /bin/sh -c $(printf '%q' "$1")"; }

echo "=== QGA ==="
"${SSH[@]}" 'qm status 905; timeout 8 qm agent 905 ping'

echo "=== DASHBOARD MATCHES ==="
qga 'grep -nEi "lighting.settings|live outdoor lux|10-minute average lux|lights on below|lights off above|path:|title:" /mnt/data/supervisor/homeassistant/dashboards/testing.yaml | tail -120'

echo "=== WESTMINSTER PACKAGE ==="
qga 'sed -n "1,260p" /mnt/data/supervisor/homeassistant/packages/ha_general_westminster.yaml'

echo "=== LUX PHASE2 PACKAGE ==="
qga 'sed -n "1,300p" /mnt/data/supervisor/homeassistant/jns/jns_lux_phase2_package.yaml'

echo "=== OUTDOOR ENVIRONMENT ==="
qga 'sed -n "1,260p" /mnt/data/supervisor/homeassistant/packages/outdoor_environment.yaml'

echo "=== AUTOMATION LUX REFERENCES ==="
qga 'grep -nEi "lux|illuminance|house_lighting|lighting_area|target_light|below|above" /mnt/data/supervisor/homeassistant/automations.yaml | tail -160'

echo "=== RESTORED LIVE STATE HINTS ==="
qga 'grep -nEi "lux|illuminance|westminster|music_player_daemon" /mnt/data/supervisor/homeassistant/.storage/core.restore_state | tail -160'
