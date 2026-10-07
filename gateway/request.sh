#!/usr/bin/env bash
set -Eeuo pipefail

echo "=== INSTALL INFRASTRUCTURE SOCKET INTERLOCKS ON HA-GENERAL (REPUBLISH) ==="
date -Is

ssh nodeb 'bash -s' <<'NODEB'
set -Eeuo pipefail

PKG=/tmp/infrastructure_power_interlocks.yaml
cat > "$PKG" <<'YAML'
# Infrastructure power interlocks
# HA-General
# Router socket currently uses the legacy entity id switch.wdnas_power_socket.
# Tuya Local config_entry_id: 01M2TRACBN3KHVCGHR65SHPAHS.
# Do not expose or use that raw switch directly for normal control.

homeassistant:
  customize:
    switch.wdnas_power_socket:
      friendly_name: "DrayTek Router Power - PROTECTED"
      icon: mdi:router-wireless

input_boolean:
  draytek_router_reboot_armed:
    name: Arm DrayTek Router Reboot
    icon: mdi:shield-key
  draytek_router_recovery_lease:
    name: DrayTek Router Recovery Lease
    icon: mdi:shield-sync
  draytek_router_reboot_cooldown:
    name: DrayTek Router Reboot Cooldown
    icon: mdi:timer-lock

script:
  draytek_router_arm_reboot:
    alias: "DrayTek Router - Arm Reboot"
    icon: mdi:shield-key
    mode: restart
    sequence:
      - action: input_boolean.turn_on
        target:
          entity_id: input_boolean.draytek_router_reboot_armed
      - delay: "00:01:00"
      - action: input_boolean.turn_off
        target:
          entity_id: input_boolean.draytek_router_reboot_armed

  draytek_router_controlled_reboot:
    alias: "DrayTek Router - Controlled Reboot"
    icon: mdi:restart-alert
    mode: single
    sequence:
      - condition: state
        entity_id: input_boolean.draytek_router_reboot_armed
        state: "on"
      - condition: state
        entity_id: input_boolean.draytek_router_reboot_cooldown
        state: "off"
      - condition: state
        entity_id: switch.wdnas_power_socket
        state: "on"
      - action: input_boolean.turn_off
        target:
          entity_id: input_boolean.draytek_router_reboot_armed
      - action: input_boolean.turn_on
        target:
          entity_id:
            - input_boolean.draytek_router_recovery_lease
            - input_boolean.draytek_router_reboot_cooldown
      - action: persistent_notification.create
        data:
          title: "DrayTek controlled reboot"
          message: "Protected router power-cycle started. Recovery lease is active."
      - action: switch.turn_off
        target:
          entity_id: switch.wdnas_power_socket
      - delay: "00:00:10"
      - action: switch.turn_on
        target:
          entity_id: switch.wdnas_power_socket
      - action: input_boolean.turn_off
        target:
          entity_id: input_boolean.draytek_router_recovery_lease
      - delay: "00:05:00"
      - action: input_boolean.turn_off
        target:
          entity_id: input_boolean.draytek_router_reboot_cooldown

automation:
  - id: infrastructure_draytek_guard_raw_off
    alias: "Infrastructure - Guard DrayTek raw power switch"
    mode: restart
    trigger:
      - platform: state
        entity_id: switch.wdnas_power_socket
        to: "off"
    condition:
      - condition: state
        entity_id: input_boolean.draytek_router_recovery_lease
        state: "off"
    action:
      - action: switch.turn_on
        target:
          entity_id: switch.wdnas_power_socket
      - action: persistent_notification.create
        data:
          title: "Protected infrastructure socket"
          message: "Direct OFF command to the DrayTek router socket was blocked and power was restored."

  - id: infrastructure_draytek_force_on_during_lease
    alias: "Infrastructure - Force DrayTek power back on"
    mode: restart
    trigger:
      - platform: state
        entity_id: switch.wdnas_power_socket
        to: "off"
    condition:
      - condition: state
        entity_id: input_boolean.draytek_router_recovery_lease
        state: "on"
    action:
      - delay: "00:00:15"
      - action: switch.turn_on
        target:
          entity_id: switch.wdnas_power_socket
      - action: input_boolean.turn_off
        target:
          entity_id: input_boolean.draytek_router_recovery_lease

  - id: infrastructure_draytek_startup_recovery
    alias: "Infrastructure - Recover DrayTek power after HA restart"
    mode: single
    trigger:
      - platform: homeassistant
        event: start
    condition:
      - condition: state
        entity_id: input_boolean.draytek_router_recovery_lease
        state: "on"
    action:
      - action: switch.turn_on
        target:
          entity_id: switch.wdnas_power_socket
      - action: input_boolean.turn_off
        target:
          entity_id: input_boolean.draytek_router_recovery_lease
      - action: persistent_notification.create
        data:
          title: "DrayTek power recovery"
          message: "HA restarted during a router reboot lease; router socket was forced ON."

  - id: infrastructure_draytek_arm_timeout_cleanup
    alias: "Infrastructure - Clear stale DrayTek arm"
    mode: restart
    trigger:
      - platform: state
        entity_id: input_boolean.draytek_router_reboot_armed
        to: "on"
        for: "00:01:05"
    action:
      - action: input_boolean.turn_off
        target:
          entity_id: input_boolean.draytek_router_reboot_armed
YAML

qm guest exec 905 -- /bin/bash -lc "mkdir -p /mnt/data/supervisor/homeassistant/packages" >/dev/null
qm guest exec 905 -- /bin/bash -lc "cat > /mnt/data/supervisor/homeassistant/packages/infrastructure_power_interlocks.yaml" --input-data "$(cat "$PKG")" >/dev/null

echo "--- Home Assistant config check ---"
qm guest exec 905 -- /bin/bash -lc "ha core check"
echo "--- Restart Home Assistant Core ---"
qm guest exec 905 -- /bin/bash -lc "ha core restart"

echo "--- Package installed ---"
qm guest exec 905 -- /bin/bash -lc "sed -n '1,260p' /mnt/data/supervisor/homeassistant/packages/infrastructure_power_interlocks.yaml"
NODEB

echo "INTERLOCK_INSTALL_COMPLETE $(date -Is)"
