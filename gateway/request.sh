#!/usr/bin/env bash
set -euo pipefail
echo "=== VALIDATE RENDERED NATURAL AUTOMATION JS ==="
ssh nodeb 'bash -s' <<'NODEB'
set -euo pipefail
curl -fsS http://127.0.0.1:8099/ >/tmp/na-page.html
python3 - <<'PY'
from pathlib import Path
h=Path("/tmp/na-page.html").read_text()
js=h.split("<script>",1)[1].rsplit("</script>",1)[0]
Path("/tmp/na-page.js").write_text(js)
for needle in ["device's","doesn't","can't","won't"]:
    if needle in js:
        print("FOUND",repr(needle))
print("js_bytes",len(js))
PY
echo "=== suspicious rendered lines ==="
grep -nE "device.s domain|doesn.t|can.t|won.t" /tmp/na-page.js || true
echo "=== JS syntax check ==="
if command -v node >/dev/null; then
  node --check /tmp/na-page.js
else
  echo "node-not-installed-on-nodeb"
fi

echo "=== direct backend progress smoke via Python ==="
python3 - <<'PY'
import json,time,urllib.request
base="http://127.0.0.1:8099"
body=json.dumps({"text":"turn on the garden waterfeature from 9am until bedtime"}).encode()
req=urllib.request.Request(base+"/api/analyse-start",body,{"Content-Type":"application/json"},method="POST")
with urllib.request.urlopen(req,timeout=5) as r:
    start=json.load(r)
print("start",start)
jid=start["job_id"]
for i in range(40):
    with urllib.request.urlopen(base+"/api/job?id="+jid,timeout=5) as r:
        j=json.load(r)
    print("poll",i,j.get("status"),j.get("stage"),(j.get("progress") or {}).get("percent"))
    if j.get("status") in ("done","error"):
        print("result",json.dumps(j.get("result"),sort_keys=True)[:2000])
        break
    time.sleep(.25)
PY
NODEB
