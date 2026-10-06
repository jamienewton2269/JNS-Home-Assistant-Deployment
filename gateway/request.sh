#!/usr/bin/env bash
set -euo pipefail

echo "=== READ NATURAL AUTOMATION QGA IMPLEMENTATION ==="
date -Is
echo "runner=$(hostname)"
echo

timeout 12s ssh -o BatchMode=yes nodeb 'python3 - <<'"'"'PY'"'"'
from pathlib import Path
p=Path("/opt/natural-automation/natural_automation.py")
lines=p.read_text(errors="ignore").splitlines()
for a,b in [(1,115),(880,970)]:
    print(f"=== LINES {a}-{b} ===")
    for n in range(a-1,min(b,len(lines))):
        s=lines[n]
        low=s.lower()
        if any(k in low for k in ("token","authorization","bearer","password","secret")):
            print(f"{n+1}: [REDACTED SENSITIVE LINE]")
        else:
            print(f"{n+1}: {s[:240]}")
PY'
