#!/usr/bin/env bash
# Verify the active Steward source exactly matches the canonical pre-UI release.
set -Eeuo pipefail
ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"
BASE_REV="4018235765a01a234234694b9d0a395ae98a6042^"
REPO_EXPECTED="$(git show "$BASE_REV:natural_automation_steward/src/natural_automation.py" | sha256sum | awk '{print $1}')"
REPO_TARGET="$(sha256sum natural_automation_steward/src/natural_automation.py | awk '{print $1}')"
echo "STEW_UI_BASE_EXPECTED_SHA=$REPO_EXPECTED"
echo "STEW_UI_TARGET_SHA=$REPO_TARGET"
SSH=(ssh -o BatchMode=yes -o StrictHostKeyChecking=yes root@nodeb.home.arpa)
REMOTE="$("${SSH[@]}" 'set -Eeuo pipefail
 test "$(hostname -s)" = nodeb
 echo "HOST_STEWARD_STATE=$(systemctl is-active natural-automation.service)"
 echo "HOST_STEWARD_PORT=$(ss -ltn | grep -c ":8099 " || true)"
 echo "HOST_STEWARD_SOURCE_SHA=$(sha256sum /opt/natural-automation/natural_automation.py | awk "{print \$1}")"
 echo "HOST_STEWARD_REPAIR_DB=$(python3 - <<PY
import sqlite3
db=sqlite3.connect("file:/opt/natural-automation/data/steward.db?mode=ro",uri=True)
print(db.execute("select count(*) from repairs").fetchone()[0])
PY
)"
')"
printf '%s\n' "$REMOTE"
LIVE_SHA="$(printf '%s\n' "$REMOTE" | sed -n 's/^HOST_STEWARD_SOURCE_SHA=//p')"
if [[ "$LIVE_SHA" != "$REPO_EXPECTED" ]]; then
 echo 'STEW_UI_BLOCKED_DIFFERENT_LIVE_SOURCE; no files changed'
 exit 74
fi
echo 'STEW_UI_BASE_SOURCE_MATCHED; safe to stage a release with rollback'
