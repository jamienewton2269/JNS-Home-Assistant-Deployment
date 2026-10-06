#!/usr/bin/env bash
set -Eeuo pipefail
echo "=== HA-GENERAL NAS CONTROL CAPABILITY CHECK ==="
date -Is
ssh nodeb '
  echo "--- HA Core ssh client ---"
  qm guest exec 905 -- /bin/bash -lc "docker exec homeassistant sh -lc \"command -v ssh || true; command -v ping || true; command -v nc || true\"" || true

  echo "--- HA config location ---"
  qm guest exec 905 -- /bin/bash -lc "ls -ld /mnt/data/supervisor/homeassistant; test -f /mnt/data/supervisor/homeassistant/configuration.yaml && echo CONFIG_OK; grep -n \"packages:\" /mnt/data/supervisor/homeassistant/configuration.yaml || true" || true

  echo "--- NAS plug entity registry match ---"
  qm guest exec 905 -- /bin/bash -lc "grep -i -n -m 10 -E \"nas[_ -]?server|nas_plug|wdnas\" /mnt/data/supervisor/homeassistant/.storage/core.entity_registry 2>/dev/null || true" || true
'
echo CHECK_COMPLETE
