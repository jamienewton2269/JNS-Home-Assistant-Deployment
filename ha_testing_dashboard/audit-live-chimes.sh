#!/usr/bin/env bash
set -Eeuo pipefail
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=yes -o HostName=10.10.110.12 nodeb)
qga(){ "${SSH[@]}" "qm guest exec 905 -- /bin/sh -c $(printf '%q' "$1")"; }

echo "=== RAIN / WEATHER ENTITIES ==="
qga 'grep -nEi "\"entity_id\":\"(binary_sensor|sensor)\.[^\"]*(rain|precip|weather|wet)[^\"]*\"" /mnt/data/supervisor/homeassistant/.storage/core.entity_registry | head -120'

echo "=== KITCHEN ENTITIES ==="
qga 'grep -nEi "\"entity_id\":\"(light|switch)\.[^\"]*(kitchen|worktop|radiator)[^\"]*\"" /mnt/data/supervisor/homeassistant/.storage/core.entity_registry | head -120'

echo "=== KITCHEN DEVICE NAMES / LABELS ==="
qga 'grep -nEi "kitchen|worktop|radiator|Lighting: Lux Controlled|Commissioned|Purpose: Standard Light" /mnt/data/supervisor/homeassistant/.storage/core.entity_registry /mnt/data/supervisor/homeassistant/.storage/core.device_registry /mnt/data/supervisor/homeassistant/.storage/core.label_registry | head -220'

echo "=== CURRENT LUX AUTOMATION BLOCK ==="
qga 'sed -n "540,660p" /mnt/data/supervisor/homeassistant/automations.yaml'

echo "=== WESTMINSTER PACKAGE HEAD ==="
qga 'sed -n "1,80p" /mnt/data/supervisor/homeassistant/packages/ha_general_westminster.yaml'
