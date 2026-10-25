#!/usr/bin/env bash
# JNS Node C runner: guarded repair-reference UI deployment, zero HA changes.
set -Eeuo pipefail
cd "$(git rev-parse --show-toplevel)"
EXPECTED="$(git show 4018235765a01a234234694b9d0a395ae98a6042^:natural_automation_steward/src/natural_automation.py | sha256sum | cut -d' ' -f1)"
test -n "$GITHUB_RUN_ID"
NODE=nodeb.home.arpa
STAGE="/tmp/jns-steward-repair-ui-$GITHUB_RUN_ID"
SRC=natural_automation_steward/src
SSH=(ssh -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=8 "root@$NODE")
SCP=(scp -q -o BatchMode=yes -o StrictHostKeyChecking=yes)
python3 -m unittest discover -s natural_automation_steward/tests -p test_repair_console.py -v
python3 -m py_compile "$SRC/natural_automation.py" "$SRC/steward/repair_console.py"
"${SSH[@]}" 'test "$(hostname -s)" = nodeb && systemctl is-active --quiet natural-automation.service'
"${SSH[@]}" "install -d -o root -g root -m 0700 '$STAGE'"
"${SCP[@]}" "$SRC/natural_automation.py" "root@$NODE:$STAGE/natural_automation.py"
"${SCP[@]}" "$SRC/steward/repair_console.py" "root@$NODE:$STAGE/repair_console.py"
MAIN="$(sha256sum "$SRC/natural_automation.py" | cut -d' ' -f1)"
MODULE="$(sha256sum "$SRC/steward/repair_console.py" | cut -d' ' -f1)"
"${SSH[@]}" "bash -s '$EXPECTED' '$MAIN' '$MODULE' '$STAGE'" <<'NODEB'
set -Eeuo pipefail
EXPECTED="$1"; MAIN="$2"; MODULE="$3"; STAGE="$4"
test "$(hostname -s)" = nodeb
test "$(id -u)" = 0
LIVE=/opt/natural-automation
BACKUP="/opt/.natural-automation-releases/repair-ui-$(date -u +%Y%m%dT%H%M%SZ)-$$"
test -d "$LIVE/steward" && test -f "$LIVE/data/steward.db"
printf '%s  %s\n' "$MAIN" "$STAGE/natural_automation.py" "$MODULE" "$STAGE/repair_console.py" | sha256sum -c - >/dev/null
CURRENT="$(sha256sum "$LIVE/natural_automation.py" | cut -d' ' -f1)"
if [[ "$CURRENT" != "$EXPECTED" ]]; then
 echo "STEW_UI_BLOCKED_DIFFERENT_SOURCE current=$CURRENT expected=$EXPECTED; no writes"
 exit 74
fi
if [[ -e "$LIVE/steward/repair_console.py" ]]; then
 echo 'STEW_UI_BLOCKED_EXISTING_MODULE; no overwrite'
 exit 73
fi
python3 -m py_compile "$STAGE/natural_automation.py" "$STAGE/repair_console.py"
mkdir -p "$BACKUP"
chmod 0700 "$BACKUP"
cp -a "$LIVE/natural_automation.py" "$BACKUP/natural_automation.py"
echo "STEW_UI_BACKUP_VERIFIED=$BACKUP"
rollback() {
  local rc="$?"
  trap - ERR
  echo "STEW_UI_ROLLBACK_START rc=$rc"
  cp -a "$BACKUP/natural_automation.py" "$LIVE/natural_automation.py"
  rm -f "$LIVE/steward/repair_console.py"
  systemctl restart natural-automation.service || true
  systemctl is-active --quiet natural-automation.service || echo 'STEW_UI_ROLLBACK_NEEDS_ATTENTION'
  exit "$rc"
}
trap rollback ERR
install -o root -g root -m 0644 "$STAGE/repair_console.py" "$LIVE/steward/repair_console.py"
install -o root -g root -m 0755 "$STAGE/natural_automation.py" "$LIVE/natural_automation.py"
python3 -m py_compile "$LIVE/natural_automation.py" "$LIVE/steward/repair_console.py"
systemctl restart natural-automation.service
ready=0
for x in $(seq 1 20); do
  if curl -fsS --max-time 6 http://127.0.0.1:8099/steward/repairs -o /tmp/jns-steward-repair-ui-check.html && grep -q 'JNS Steward Repair Centre' /tmp/jns-steward-repair-ui-check.html; then ready=1; break; fi
  sleep 1
done
test "$ready" = 1
curl -fsS -X POST --max-time 14 -H 'Content-Type: application/json' -d '{"query":"zigbee"}' http://127.0.0.1:8099/api/steward/repair-search | python3 -c 'import json,sys;v=json.load(sys.stdin);assert v["ok"] and v["result_count"]>=1 and v["fixes_applied"]==0 and v["execution_authority"]=="none";print("STEW_UI_LIVE_SEARCH_OK",v["result_count"])'
curl -fsS --max-time 15 http://127.0.0.1:8099/api/status | python3 -c 'import json,sys;v=json.load(sys.stdin);assert v["ok"] and v["target"]["role"]=="ha-general";print("STEW_UI_RUNTIME_OK",v["target"]["vmid"])'
test "$(sha256sum "$LIVE/natural_automation.py" | cut -d' ' -f1)" = "$MAIN"
systemctl is-active --quiet natural-automation.service
trap - ERR
echo "STEW_UI_DEPLOYED_OK_NO_HOME_ASSISTANT_RESTART"
NODEB
