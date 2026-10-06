#!/usr/bin/env bash
set -euo pipefail

echo "=== HA-GENERAL LOVELACE BLOCK ==="
date -Is
echo "runner=$(hostname)"
echo

timeout 20s ssh -o BatchMode=yes nodeb 'bash -s' <<'REMOTE'
set -euo pipefail
cd /opt/natural-automation
python3 - <<'PY'
import natural_automation as na
code = r"""
from pathlib import Path
lines=Path('/config/configuration.yaml').read_text(errors='ignore').splitlines()
start=None
for i,l in enumerate(lines):
    if l.startswith('lovelace:'):
        start=i
        break
if start is None:
    print('NO_LOVELACE')
else:
    end=len(lines)
    for j in range(start+1,len(lines)):
        l=lines[j]
        if l and not l[0].isspace() and not l.startswith('#'):
            end=j
            break
    print('\n'.join(lines[start:end]))
"""
print(na.qga_python(code, timeout=12))
PY
REMOTE
