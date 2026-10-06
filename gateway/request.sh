#!/usr/bin/env bash
set -euo pipefail
ssh nodea 'bash -s' <<'REMOTE'
set -Eeuo pipefail
for id in 902 903 905; do
  echo
  echo "=== OFFLINE BOOT TEST VM$id ==="
  qm status "$id" | grep -q '^status: stopped$'
  cfg="$(qm config "$id")"
  grep -Eq '^net0: .*link_down=1' <<<"$cfg"
  grep -q '^onboot: 0$' <<<"$cfg"
  grep -Eq '^(usb|hostpci)[0-9]+:' <<<"$cfg" && { echo "REFUSE passthrough present"; exit 77; } || true

  qm start "$id"
  ready=0
  for n in $(seq 1 30); do
    if timeout 5s qm guest cmd "$id" ping >/dev/null 2>&1; then ready=1; break; fi
    sleep 3
  done
  echo "QGA_READY=$ready"
  qm status "$id"
  if [ "$ready" -eq 1 ]; then
    echo "--- OS INFO ---"
    timeout 8s qm guest cmd "$id" get-osinfo 2>&1 || true
    echo "--- GUEST NETWORK ---"
    timeout 8s qm guest cmd "$id" network-get-interfaces 2>&1 | head -120 || true
    echo "--- HA CORE PROBE ---"
    timeout 15s qm guest exec "$id" -- /bin/bash -lc 'ha core info 2>/dev/null | head -40 || true' 2>&1 || true
  fi
  qm shutdown "$id" --timeout 90 || qm stop "$id"
  for n in $(seq 1 20); do
    qm status "$id" | grep -q '^status: stopped$' && break
    sleep 2
  done
  qm status "$id"
  qm config "$id" | grep -E '^(net0|onboot):'
  qm status "$id" | grep -q '^status: stopped$'
  qm config "$id" | grep -Eq '^net0: .*link_down=1'
  echo "OFFLINE_BOOT_TEST_VM$id=PASS"
done
REMOTE
