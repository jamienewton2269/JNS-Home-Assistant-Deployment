#!/usr/bin/env bash
set -Eeuo pipefail
echo "=== PREPARE XIGMANAS CONTROL KEY ==="
date -Is
ssh nodeb '
  set -Eeuo pipefail
  install -d -m 700 /root/.ssh
  key=/root/.ssh/jns_xigmanas_ed25519
  if [ ! -f "$key" ]; then
    ssh-keygen -q -t ed25519 -N "" -C "ha-general-xigmanas-control" -f "$key"
    chmod 600 "$key"
    chmod 644 "$key.pub"
    echo KEY_CREATED
  else
    echo KEY_ALREADY_PRESENT
  fi
  echo PUBLIC_KEY_BEGIN
  cat "$key.pub"
  echo PUBLIC_KEY_END
  echo "--- HA config path ---"
  qm guest exec 905 -- /bin/bash -lc "ls -ld /mnt/data/supervisor/homeassistant 2>/dev/null || true; test -f /mnt/data/supervisor/homeassistant/configuration.yaml && echo CONFIG_OK || true" || true
'
echo PREP_COMPLETE
