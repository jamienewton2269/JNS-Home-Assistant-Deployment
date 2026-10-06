#!/usr/bin/env bash
set -Eeuo pipefail

echo "=== XIGMANAS / HA-GENERAL CONTROL PRECHECK ==="
date -Is

echo "--- HA-General VM905 on Node B ---"
ssh nodeb '
  qm status 905 || true
  echo "--- QGA ---"
  qm guest cmd 905 ping >/dev/null 2>&1 && echo QGA_OK || echo QGA_UNAVAILABLE
  echo "--- HA core info ---"
  qm guest exec 905 -- /bin/bash -lc "ha core info 2>/dev/null | head -40" 2>/dev/null || true
'

echo "--- XigmaNAS reachability from Node C runner ---"
ping -c 1 -W 2 10.10.10.221 >/dev/null 2>&1 && echo NAS_PING=UP || echo NAS_PING=DOWN
for port in 22 80 443; do
  timeout 3 bash -c "</dev/tcp/10.10.10.221/$port" >/dev/null 2>&1 && echo "NAS_TCP_$port=OPEN" || echo "NAS_TCP_$port=CLOSED"
done

echo "--- Existing SSH trust to XigmaNAS ---"
if ssh -o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=accept-new root@10.10.10.221 'echo NODEC_TO_NAS_SSH_OK' 2>/dev/null; then
  :
else
  echo NODEC_TO_NAS_SSH=NO_KEY_OR_LOGIN
fi

echo "--- Node B SSH trust to XigmaNAS ---"
ssh nodeb '
  if ssh -o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=accept-new root@10.10.10.221 "echo NODEB_TO_NAS_SSH_OK" 2>/dev/null; then
    :
  else
    echo NODEB_TO_NAS_SSH=NO_KEY_OR_LOGIN
  fi
'

echo "--- HA-General config visibility ---"
ssh nodeb '
  qm guest exec 905 -- /bin/bash -lc "
    echo HOSTNAME=\\\$(hostname)
    ls -ld /config 2>/dev/null || true
    test -f /config/configuration.yaml && echo CONFIG_YAML_PRESENT || true
  " 2>/dev/null || true
'

echo PRECHECK_COMPLETE
