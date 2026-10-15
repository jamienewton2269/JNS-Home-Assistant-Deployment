#!/usr/bin/env bash
set -Eeuo pipefail
RUNAS=(runuser -u github-runner -- ssh -o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=yes -o HostName=10.10.10.235 nodeb)

echo "=== WESTMINSTER FILE LOCATIONS ==="
"${RUNAS[@]}" "qm guest exec 905 -- /bin/sh -c 'grep -RliE "jns_westminster|westminster_chimes_half_and_hour" /mnt/data/supervisor/homeassistant 2>/dev/null | head -40'"

echo
echo "=== LIGHTING SETTINGS VIEW ==="
"${RUNAS[@]}" "qm guest exec 905 -- /bin/sh -c 'python3 - <<"PY"
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
PY'"
