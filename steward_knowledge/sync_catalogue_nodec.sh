#!/usr/bin/env bash
# Node C GitHub runner -> on-site Steward SQLite, no HA restarts or script execution.
set -Eeuo pipefail
test -n "${GITHUB_RUN_ID:-}" && test -n "${GITHUB_SHA:-}"
ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"
PY=natural_automation_steward/tools/sync_repair_catalogue_v2.py
SEED="/tmp/jns-steward-repairs-$GITHUB_RUN_ID.json"
NODE=nodeb.home.arpa
REMOTE="/tmp/jns-steward-repair-$GITHUB_RUN_ID"
trap 'rm -f "$SEED"' EXIT
python3 -m py_compile "$PY" steward_knowledge/verify_catalogue_live.py
python3 -m unittest discover -s natural_automation_steward/tests -p test_catalogue_v2.py -v
python3 "$PY" --repo-root . --export-json "$SEED"
COUNT="$(python3 - "$SEED" "$GITHUB_SHA" <<'PY'
import json,sys
p=json.load(open(sys.argv[1]))
assert p["repo_commit"]==sys.argv[2],"git commit mismatch"
assert p["record_count"]>=100
assert all(x["safety_class"]=="manual_review" and not x["portable"] for x in p["records"])
print(p["record_count"])
PY
)"
echo "JNS_STEWARD_REPAIR_PREFLIGHT_OK record_count=$COUNT"
SSH=(ssh -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=8 "root@$NODE")
SCP=(scp -q -o BatchMode=yes -o StrictHostKeyChecking=yes)
"${SSH[@]}" 'test "$(hostname -s)" = nodeb && test -f /opt/natural-automation/data/steward.db && systemctl is-active --quiet natural-automation.service'
"${SSH[@]}" "install -d -m 0700 '$REMOTE'"
"${SCP[@]}" "$PY" "root@$NODE:$REMOTE/loader.py"
"${SCP[@]}" steward_knowledge/verify_catalogue_live.py "root@$NODE:$REMOTE/verify.py"
"${SCP[@]}" "$SEED" "root@$NODE:$REMOTE/seed.json"
SUM_PY="$(sha256sum "$PY" | cut -d' ' -f1)"
SUM_SEED="$(sha256sum "$SEED" | cut -d' ' -f1)"
SUM_VERIFY="$(sha256sum steward_knowledge/verify_catalogue_live.py | cut -d' ' -f1)"
"${SSH[@]}" "set -Eeuo pipefail
  cd '$REMOTE'
  printf '%s  %s\n' '$SUM_PY' loader.py '$SUM_SEED' seed.json '$SUM_VERIFY' verify.py | sha256sum -c - >/dev/null
  python3 -m py_compile loader.py verify.py
  flock -n /run/lock/jns-steward-repair-catalogue.lock \
    python3 loader.py --db /opt/natural-automation/data/steward.db --import-json seed.json
  python3 verify.py '$GITHUB_SHA' '$COUNT'
  systemctl is-active --quiet natural-automation.service
"
echo JNS_STEWARD_REPAIR_SYNC_OK_NO_HA_RESTART
