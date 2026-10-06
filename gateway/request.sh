#!/usr/bin/env bash
set -euo pipefail

echo "=== HA-GENERAL DASHBOARD DEPLOYMENT PRECHECK ==="
date -Is
echo "runner=$(hostname)"
echo

sudo -u jns-mcp ssh -o BatchMode=yes node-b 'bash -s' <<'REMOTE'
set -euo pipefail

echo "=== VM905 CONFIG/STATUS ==="
qm status 905
qm config 905 | sed -n '1,80p'

echo
echo "=== VM905 GUEST NETWORK ==="
qm guest cmd 905 network-get-interfaces 2>&1 | sed -n '1,160p' || true

echo
echo "=== HA HTTP ==="
python3 - <<'PY'
import urllib.request
for u in ("http://10.10.10.223/","http://10.10.10.223/api/"):
    try:
        r=urllib.request.urlopen(u,timeout=5)
        print(u, r.status, r.headers.get("Server",""))
    except Exception as e:
        print(u, type(e).__name__, str(e)[:160])
PY

echo
echo "=== NATURAL AUTOMATION FILES ==="
find /opt/natural-automation -maxdepth 2 -type f -printf '%p\n' 2>/dev/null | sort | sed -n '1,200p'

echo
echo "=== NATURAL AUTOMATION SERVICES/STATUS ==="
systemctl --no-pager --full status natural-automation 2>/dev/null | sed -n '1,60p' || true
curl -fsS http://127.0.0.1:8099/api/status 2>/dev/null || true
echo

echo
echo "=== NON-SECRET CONFIG KEYS ==="
python3 - <<'PY'
from pathlib import Path
import re
for p in Path('/opt/natural-automation').rglob('*'):
    if not p.is_file() or p.stat().st_size > 300000:
        continue
    if p.suffix.lower() not in ('.py','.json','.yaml','.yml','.env','.conf','.ini',''):
        continue
    try:
        txt=p.read_text(errors='ignore')
    except Exception:
        continue
    hits=[]
    for pat in [r'HA_URL\s*[:=][^\n]+',r'HOME_ASSISTANT[^\n]{0,100}',r'10\.10\.10\.223[^\n]{0,100}',r'/api/[^\s\"\']+']:
        for m in re.findall(pat,txt,re.I):
            s=m if isinstance(m,str) else str(m)
            s=re.sub(r'(?i)(token|authorization|bearer|password|secret)\s*[:=]\s*[^\s,}\]]+',
                     r'\1=[REDACTED]',s)
            if 'token' in s.lower() or 'authorization' in s.lower() or 'bearer' in s.lower() or 'password' in s.lower() or 'secret' in s.lower():
                continue
            hits.append(s[:180])
    if hits:
        print(p)
        for h in sorted(set(hits))[:12]:
            print(' ',h)
PY
REMOTE
