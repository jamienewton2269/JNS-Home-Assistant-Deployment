#!/usr/bin/env bash
set -euo pipefail
echo "=== FIX STEWARD SQLITE THREAD SAFETY + ACCEPTANCE TEST ==="
date -Is
ssh nodeb 'bash -s' <<'NODEB'
set -euo pipefail
python3 - <<'PY'
from pathlib import Path
p=Path("/opt/natural-automation/steward/store.py")
s=p.read_text()
s=s.replace("import json, sqlite3, time","import json, sqlite3, time, threading")
s=s.replace("self.db=sqlite3.connect(self.path)","self.lock=threading.RLock()\n        self.db=sqlite3.connect(self.path,check_same_thread=False)")
s=s.replace("""    def set_fact(self,namespace,key,value):
        self.db.execute(""","""    def set_fact(self,namespace,key,value):
        with self.lock:
            self.db.execute(""")
s=s.replace("""          (namespace,key,json.dumps(value,sort_keys=True),time.time()))
        self.db.commit()
    def observe""","""          (namespace,key,json.dumps(value,sort_keys=True),time.time()))
            self.db.commit()
    def observe""")
s=s.replace("""    def observe(self,kind,source,payload):
        self.db.execute(""","""    def observe(self,kind,source,payload):
        with self.lock:
            self.db.execute(""")
s=s.replace("""          (time.time(),kind,source,json.dumps(payload,sort_keys=True)))
        self.db.commit()
    def status(self):
        return {""","""          (time.time(),kind,source,json.dumps(payload,sort_keys=True)))
            self.db.commit()
    def status(self):
        with self.lock:
            return {""")
p.write_text(s)
PY

python3 -m py_compile /opt/natural-automation/steward/store.py /opt/natural-automation/natural_automation.py
systemctl restart natural-automation
sleep 2

echo "=== STATUS ==="
curl -sS http://127.0.0.1:8099/api/status; echo
echo "=== STEWARD STATUS ==="
curl -sS -X POST -H 'Content-Type: application/json' -d '{}' http://127.0.0.1:8099/api/steward/status; echo

echo "=== APPLY SAFETY TEST: unresolved must reject, no write ==="
before=$(qm guest exec 905 -- docker exec homeassistant python3 -c "import hashlib,os; p='/config/natural_automation.yaml'; print(hashlib.sha256(open(p,'rb').read()).hexdigest() if os.path.exists(p) else 'MISSING')" | python3 -c 'import sys,json; print(json.load(sys.stdin).get("out-data","").strip())')
code=$(curl -sS -o /tmp/na-reject.json -w '%{http_code}' -X POST -H 'Content-Type: application/json' \
  -d '{"unresolved":["test unresolved target"],"automation":{"alias":"SHOULD NOT WRITE","trigger":[{"platform":"time","at":"23:59:59"}],"action":[{"service":"light.turn_off","target":{"entity_id":"light.invalid_test"}}]}}' \
  http://127.0.0.1:8099/api/apply-automation)
cat /tmp/na-reject.json; echo
echo "http_code=$code"
after=$(qm guest exec 905 -- docker exec homeassistant python3 -c "import hashlib,os; p='/config/natural_automation.yaml'; print(hashlib.sha256(open(p,'rb').read()).hexdigest() if os.path.exists(p) else 'MISSING')" | python3 -c 'import sys,json; print(json.load(sys.stdin).get("out-data","").strip())')
echo "before=$before"
echo "after=$after"
test "$before" = "$after"
test "$code" = "409"

echo "=== HA-GENERAL CONFIG CHECK ==="
qm guest exec 905 -- ha core check

echo "=== SERVICE LOG TAIL ==="
journalctl -u natural-automation -n 25 --no-pager
echo "ACCEPTANCE_OK"
NODEB
