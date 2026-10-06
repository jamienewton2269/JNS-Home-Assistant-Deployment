#!/usr/bin/env bash
set -euo pipefail

echo "=== HA-GENERAL LIVE LOVELACE INSPECTION ==="
date -Is
echo "runner=$(hostname)"
echo

timeout 20s ssh -o BatchMode=yes nodeb 'bash -s' <<'REMOTE'
set -euo pipefail
cd /opt/natural-automation

python3 - <<'PY'
import json
import natural_automation as na

code = r"""
from pathlib import Path
import json
root=Path('/config')
cfg=(root/'configuration.yaml').read_text(errors='ignore')
storage=[]
for p in (root/'.storage').glob('lovelace*'):
    try:
        storage.append({'name':p.name,'size':p.stat().st_size})
    except Exception:
        pass
print(json.dumps({
  'lovelace_lines':[x for x in cfg.splitlines() if x.startswith('lovelace:')],
  'testing_yaml_exists':(root/'testing-dashboard.yaml').exists(),
  'storage':storage,
  'www_exists':(root/'www').exists(),
},separators=(',',':')))
"""
print(na.qga_python(code, timeout=12))
PY
REMOTE
