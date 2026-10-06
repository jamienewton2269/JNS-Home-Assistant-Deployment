#!/usr/bin/env bash
set -euo pipefail

echo "=== FINAL HA-GENERAL DNS + TESTING DASHBOARD VERIFY ==="
date -Is
echo "runner=$(hostname)"
echo

echo "=== NODE C CLIENT DNS ==="
getent hosts ha-general.home.arpa || true
getent hosts ha-general || true
echo

echo "=== DOCUMENTATION CATALOGUE ==="
id
ls -ld /home/github-runner/steward-web/docs 2>/dev/null || true
ls -l /home/github-runner/steward-web/docs/script-catalogue.txt 2>/dev/null || true
if sudo -n true 2>/dev/null; then
  sudo -n sh -c '
    f=/home/github-runner/steward-web/docs/script-catalogue.txt
    mkdir -p "$(dirname "$f")"
    touch "$f"
    tmp=$(mktemp)
    grep -v "^deploy-ha-general-testing\.sh - " "$f" > "$tmp" || true
    echo "deploy-ha-general-testing.sh - Deploys the stable ha-general.home.arpa DNS name and the HA-General Testing dashboard with automatic light/switch/fan/sensor discovery and native HA commissioning via Areas and Labels; validates configuration before restart." >> "$tmp"
    cat "$tmp" > "$f"
    rm -f "$tmp"
  '
  echo "catalogue=updated"
else
  echo "catalogue=not-updated-no-runner-sudo"
fi
echo

timeout 20s ssh -o BatchMode=yes nodeb 'bash -s' <<'REMOTE'
set -euo pipefail
cd /opt/natural-automation

echo "=== HA LOVELACE CONFIG ==="
python3 - <<'PY'
import natural_automation as na
code=r"""
from pathlib import Path
lines=Path('/config/configuration.yaml').read_text(errors='ignore').splitlines()
start=next(i for i,l in enumerate(lines) if l.startswith('lovelace:'))
end=len(lines)
for j in range(start+1,len(lines)):
    if lines[j] and not lines[j][0].isspace() and not lines[j].startswith('#'):
        end=j; break
print('\n'.join(lines[start:end]))
print('--- TESTING FILE ---')
p=Path('/config/dashboards/testing.yaml')
print('exists=',p.exists(),'bytes=',p.stat().st_size if p.exists() else 0)
print('\n'.join(p.read_text(errors='ignore').splitlines()[:18]) if p.exists() else '')
"""
print(na.qga_python(code,timeout=12))
PY

echo "=== HTTP VERIFY ==="
curl -sS -o /dev/null -w 'root=%{http_code}\n' --max-time 4 http://10.10.10.223/
curl -sS -o /dev/null -w 'testing=%{http_code}\n' --max-time 4 http://10.10.10.223/testing-dashboard/controls
curl -sS -o /dev/null -w 'commissioning=%{http_code}\n' --max-time 4 http://10.10.10.223/testing-dashboard/commissioning
REMOTE
