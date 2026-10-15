#!/usr/bin/env bash
set -Eeuo pipefail
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=yes -o HostName=10.10.10.235 nodeb)

echo "=== WESTMINSTER FILE LOCATIONS ==="
"${SSH[@]}" "qm guest exec 905 -- /bin/sh -c 'grep -RliE \"jns_westminster|westminster_chimes_half_and_hour\" /mnt/data/supervisor/homeassistant 2>/dev/null | head -40'"

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
