#!/usr/bin/env bash
set -Eeuo pipefail
SSH=(sudo -u github-runner ssh -o BatchMode=yes -o ConnectTimeout=10 -o HostName=10.10.10.235 nodeb)
CMD="sed -n '180,310p' /mnt/data/supervisor/homeassistant/dashboards/testing.yaml"
echo "Inspecting protected tab and commissioning logic..."
timeout 30 "${SSH[@]}" "timeout 15 qm guest exec 905 -- /bin/sh -c $(printf '%q' "$CMD")"
echo "READ-ONLY COMPLETE"
