#!/usr/bin/env bash
set -euo pipefail
ssh nodeb 'python3 - <<"PY"
from pathlib import Path
p=Path("/opt/natural-automation/natural_automation.py")
s=p.read_text()
a=s.index("HTML=\"\"\"")
b=s.index("ADMIN_HTML=\"\"\"")
html=s[a:b]
html=html.replace("\\\x27","\\\\\\\x27")
html=html.replace("Development Node B · HA Lite VM902 · language learning test","Node B · HA-General VM905 · Natural Automation + Steward")
html=html.replace("Live development view. Write gate remains disabled.","Live HA-General view. Controlled automation writes enabled; repair/configuration writes remain gated.")
p.with_suffix(".py.pre-ui-fix").write_text(s)
p.write_text(s[:a]+html+s[b:])
PY
python3 -m py_compile /opt/natural-automation/natural_automation.py
systemctl restart natural-automation
sleep 2
curl -fsS http://127.0.0.1:8099/ >/tmp/na-page.html
python3 - <<"PY"
from pathlib import Path
h=Path("/tmp/na-page.html").read_text()
print("label_ok", "HA-General VM905" in h)
print("write_text_ok", "Controlled automation writes enabled" in h)
js=h.split("<script>",1)[1].rsplit("</script>",1)[0]
Path("/tmp/na-page.js").write_text(js)
PY
node --check /tmp/na-page.js
curl -fsS http://127.0.0.1:8099/api/status
echo
echo UI_SYNTAX_OK
'