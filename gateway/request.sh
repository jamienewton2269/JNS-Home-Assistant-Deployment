#!/usr/bin/env bash
set -euo pipefail

echo "=== ENABLE AND VERIFY HA-GENERAL DNS ==="
date -Is
echo "runner=$(hostname)"
echo

timeout 20s ssh -o BatchMode=yes nodeb 'bash -s' <<'REMOTE'
set -euo pipefail
pct exec 218 -- python3 - <<'PY'
from pathlib import Path
p=Path("/opt/AdGuardHome/AdGuardHome.yaml")
lines=p.read_text().splitlines()
targets={"ha-general.home.arpa","ha-general"}
current=None
for i,line in enumerate(lines):
    s=line.strip()
    if s.startswith("- domain:"):
        current=s.split(":",1)[1].strip()
    elif current in targets and s.startswith("enabled:"):
        indent=line[:len(line)-len(line.lstrip())]
        lines[i]=indent+"enabled: true"
        current=None
p.write_text("\n".join(lines)+"\n")
PY
pct exec 218 -- systemctl restart AdGuardHome
pct exec 218 -- systemctl is-active AdGuardHome
echo
pct exec 218 -- sh -lc 'nslookup ha-general.home.arpa 127.0.0.1; echo; nslookup ha-general 127.0.0.1; echo; grep -A10 "rewrites:" /opt/AdGuardHome/AdGuardHome.yaml'
REMOTE
