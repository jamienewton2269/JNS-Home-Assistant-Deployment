#!/usr/bin/env bash
set -euo pipefail

echo "=== ADD HA-GENERAL DNS + INSPECT HA CONTROL API ==="
date -Is
echo "runner=$(hostname)"
echo

timeout 20s ssh -o BatchMode=yes nodeb 'bash -s' <<'REMOTE'
set -euo pipefail

echo "=== ADGUARD CURRENT REWRITES ==="
pct exec 218 -- python3 - <<'PY'
from pathlib import Path
p=Path("/opt/AdGuardHome/AdGuardHome.yaml")
txt=p.read_text()
lines=txt.splitlines()
for i,line in enumerate(lines):
    if line.lstrip().startswith("rewrites:"):
        for x in lines[max(0,i-3):min(len(lines),i+40)]:
            print(x)
        break
else:
    print("NO_REWRITES_SECTION")
PY

echo
echo "=== NATURAL AUTOMATION HA ACCESS FUNCTIONS ==="
python3 - <<'PY'
from pathlib import Path
p=Path('/opt/natural-automation/natural_automation.py')
lines=p.read_text(errors='ignore').splitlines()
terms=('ha_request','ha_api','api/states','api/services','lovelace','websocket','entity_registry','config/')
seen=set()
for i,line in enumerate(lines):
    low=line.lower()
    if any(t in low for t in terms):
        a=max(0,i-4); b=min(len(lines),i+9)
        key=(a,b)
        if key in seen: continue
        seen.add(key)
        print(f"--- lines {a+1}-{b} ---")
        for n in range(a,b):
            s=lines[n]
            if any(k in s.lower() for k in ('token','authorization','bearer','password','secret')):
                print(f"{n+1}: [REDACTED SENSITIVE LINE]")
            else:
                print(f"{n+1}: {s[:220]}")
PY
REMOTE
