#!/usr/bin/env bash
set -euo pipefail

echo "=== FIX AND VALIDATE HA-GENERAL TESTING DASHBOARD YAML ==="
date -Is
echo "runner=$(hostname)"
echo

DASH="ha_testing_dashboard/testing-dashboard.yaml"
[[ -f "$DASH" ]] || { echo "Missing $DASH" >&2; exit 1; }

echo "Sending corrected dashboard payload to Node B..."
base64 -w0 "$DASH" | timeout 10s ssh -o BatchMode=yes nodeb 'cat >/tmp/jns-testing-dashboard.b64'

timeout 30s ssh -o BatchMode=yes nodeb 'python3 - <<'"'"'PY'"'"'
from pathlib import Path
import sys, json
sys.path.insert(0,"/opt/natural-automation")
import natural_automation as na

b64=Path("/tmp/jns-testing-dashboard.b64").read_text().strip()

code=f"""
from pathlib import Path
import base64, yaml, shutil, time, json

target=Path('/config/dashboards/testing.yaml')
payload=base64.b64decode({b64!r})

# Parse before touching the live file.
parsed=yaml.safe_load(payload)
if not isinstance(parsed, dict) or 'views' not in parsed:
    raise RuntimeError('Testing dashboard YAML parsed but does not contain a top-level views list')

backup=target.with_name('testing.yaml.jns-fix-' + time.strftime('%Y%m%d-%H%M%S') + '.bak')
if target.exists():
    shutil.copy2(target, backup)

target.write_bytes(payload)

# Re-read and parse the actual live file after write.
live=yaml.safe_load(target.read_text())
if not isinstance(live, dict) or not isinstance(live.get('views'), list):
    raise RuntimeError('Live Testing dashboard failed post-write validation')

print(json.dumps({{
    'ok': True,
    'backup': str(backup),
    'bytes': target.stat().st_size,
    'views': [v.get('title') for v in live.get('views',[])],
}}, separators=(',',':')))
"""

print(na.qga_python(code, timeout=15))
Path("/tmp/jns-testing-dashboard.b64").unlink(missing_ok=True)
PY'

echo
echo "=== HTTP VERIFY ==="
timeout 10s ssh -o BatchMode=yes nodeb "curl -sS -o /dev/null -w 'testing=%{http_code}\n' --max-time 4 http://10.10.10.223/testing-dashboard/commissioning"
