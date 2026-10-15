#!/usr/bin/env bash
set -Eeuo pipefail
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=yes -o HostName=10.10.110.12 nodeb)

echo "=== VM / QGA / HA STATUS ==="
"${SSH[@]}" 'qm status 905; timeout 8 qm agent 905 ping; qm guest exec 905 -- /bin/sh -c "ha core info 2>&1 || true"'

echo
echo "=== WESTMINSTER FILE LOCATIONS ==="
"${SSH[@]}" "qm guest exec 905 -- /bin/sh -c 'grep -RliE \"jns_westminster|westminster_chimes_half_and_hour\" /mnt/data/supervisor/homeassistant 2>/dev/null | head -40'"

echo
echo "=== LUX / LIGHTING FILE LOCATIONS ==="
"${SSH[@]}" "qm guest exec 905 -- /bin/sh -c 'grep -RliE \"Live outdoor lux|10-minute average lux|Lights ON below|lighting-settings|hysteresis|lux\" /mnt/data/supervisor/homeassistant 2>/dev/null | head -80'"

echo
echo "=== LIGHTING SETTINGS VIEW ==="
PYCODE=$(cat <<'PY'
from pathlib import Path
p=Path("/mnt/data/supervisor/homeassistant/dashboards/testing.yaml")
text=p.read_text()
lines=text.splitlines()
for i,l in enumerate(lines):
    if "path: lighting-settings" in l:
        start=max(0,i-3)
        end=len(lines)
        for j in range(i+1,len(lines)):
            if lines[j].startswith("  - title:"):
                end=j
                break
        print("\n".join(f"{n+1}: {lines[n]}" for n in range(start,end)))
        break
else:
    print("lighting-settings view not found")
PY
)
B64=$(printf '%s' "$PYCODE" | base64 -w0)
"${SSH[@]}" "qm guest exec 905 -- /usr/bin/python3 -c \"import base64;exec(base64.b64decode('$B64'))\""

echo
echo "=== RELEVANT ENTITY REGISTRY ==="
"${SSH[@]}" "qm guest exec 905 -- /bin/sh -c 'grep -nEi \"westminster|lux|illuminance|daylight|ambient\" /mnt/data/supervisor/homeassistant/.storage/core.entity_registry 2>/dev/null | head -100'"
