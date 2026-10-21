#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SEED_JSON=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --seed)
      SEED_JSON="${2:?seed path required}"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 64
      ;;
  esac
done

[[ $EUID -eq 0 ]] || { echo "Run as root" >&2; exit 77; }

SRC="$ROOT_DIR/src"
SERVICE="$ROOT_DIR/systemd/natural-automation.service"
TOOLS="$ROOT_DIR/tools"
VERSION_FILE="$ROOT_DIR/VERSION"
LIVE=/opt/natural-automation
REAL=/opt/real-progress
RELEASES=/opt/.natural-automation-releases
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP="$RELEASES/v1-pre-$STAMP"

for required in   "$SRC/natural_automation.py"   "$SRC/steward/store.py"   "$SRC/steward/writer.py"   "$SRC/steward/target.py"   "$SRC/steward/proposals.py"   "$SERVICE"   "$TOOLS/seed_repairs.py"   "$VERSION_FILE"
do
  [[ -f "$required" ]] || { echo "Missing release file: $required" >&2; exit 66; }
done

mkdir -p "$BACKUP" "$LIVE/data"
if [[ -f "$LIVE/natural_automation.py" ]]; then
  cp -a "$LIVE/natural_automation.py" "$BACKUP/"
fi
if [[ -d "$LIVE/steward" ]]; then
  cp -a "$LIVE/steward" "$BACKUP/steward"
fi
if [[ -d "$REAL" ]]; then
  cp -a "$REAL" "$BACKUP/real-progress"
fi
if [[ -f /etc/systemd/system/natural-automation.service ]]; then
  cp -a /etc/systemd/system/natural-automation.service "$BACKUP/natural-automation.service"
fi
if [[ -f "$LIVE/data/steward.db" ]]; then
  cp -a "$LIVE/data/steward.db" "$BACKUP/steward.db"
fi
if [[ -f "$LIVE/VERSION" ]]; then
  cp -a "$LIVE/VERSION" "$BACKUP/VERSION"
fi

# If a previous v1 attempt copied canonical source but failed before completion,
# retain the oldest pre-v1 snapshot as the rollback baseline.
ROLLBACK_SOURCE="$BACKUP"
if [[ -f "$LIVE/natural_automation.py" ]] &&    grep -q 'TARGET_RESOLVER=TargetResolver()' "$LIVE/natural_automation.py"; then
  candidate="$(
    find "$RELEASES" -mindepth 1 -maxdepth 1 -type d -name 'v1-pre-*' -print |
      LC_ALL=C sort | head -1
  )"
  if [[ -n "$candidate" && "$candidate" != "$BACKUP" && -f "$candidate/natural_automation.py" ]]; then
    ROLLBACK_SOURCE="$candidate"
  fi
fi

cat > "$BACKUP/rollback.sh" <<EOF
#!/usr/bin/env bash
set -Eeuo pipefail
SOURCE="$ROLLBACK_SOURCE"
LIVE="$LIVE"
REAL="$REAL"
systemctl stop natural-automation.service || true
if [[ -f "\$SOURCE/natural_automation.py" ]]; then
  cp -a "\$SOURCE/natural_automation.py" "\$LIVE/natural_automation.py"
fi
if [[ -d "\$SOURCE/steward" ]]; then
  rm -rf "\$LIVE/steward"
  cp -a "\$SOURCE/steward" "\$LIVE/steward"
fi
if [[ -d "\$SOURCE/real-progress" ]]; then
  rm -rf "\$REAL"
  cp -a "\$SOURCE/real-progress" "\$REAL"
fi
if [[ -f "\$SOURCE/natural-automation.service" ]]; then
  cp -a "\$SOURCE/natural-automation.service" /etc/systemd/system/natural-automation.service
fi
if [[ -f "\$SOURCE/steward.db" ]]; then
  cp -a "\$SOURCE/steward.db" "\$LIVE/data/steward.db"
fi
if [[ -f "\$SOURCE/VERSION" ]]; then
  cp -a "\$SOURCE/VERSION" "\$LIVE/VERSION"
else
  rm -f "\$LIVE/VERSION"
fi
systemctl daemon-reload
systemctl restart natural-automation.service
EOF
chmod 0750 "$BACKUP/rollback.sh"

rollback_on_error() {
  rc=$?
  echo "INSTALL_FAILED rc=$rc; restoring $ROLLBACK_SOURCE" >&2
  bash "$BACKUP/rollback.sh" || true
  exit "$rc"
}
trap rollback_on_error ERR

mkdir -p "$LIVE/steward" "$LIVE/tools" "$REAL"
install -m 0755 "$SRC/natural_automation.py" "$LIVE/natural_automation.py"
find "$LIVE/steward" -maxdepth 1 -type f -name '*.py' -delete
install -m 0644 "$SRC"/steward/*.py "$LIVE/steward/"
install -m 0755 "$TOOLS/seed_repairs.py" "$LIVE/tools/seed_repairs.py"
install -m 0644 "$VERSION_FILE" "$LIVE/VERSION"

find "$REAL" -maxdepth 1 -type f -name '*.py' -delete
install -m 0644 "$SRC"/real_progress/*.py "$REAL/"

install -m 0644 "$SERVICE" /etc/systemd/system/natural-automation.service

python3 -m compileall -q "$LIVE" "$REAL"

if [[ -n "$SEED_JSON" ]]; then
  [[ -f "$SEED_JSON" ]] || { echo "Seed file missing: $SEED_JSON" >&2; exit 66; }
  python3 "$LIVE/tools/seed_repairs.py"     --db "$LIVE/data/steward.db"     --import-json "$SEED_JSON"
fi

systemctl daemon-reload
systemctl restart natural-automation.service
sleep 2
systemctl is-active --quiet natural-automation.service

trap - ERR
echo "INSTALL_OK"
echo "version=$(tr -d '\r\n' < "$LIVE/VERSION")"
echo "backup=$BACKUP"
echo "rollback_source=$ROLLBACK_SOURCE"
echo "rollback=$BACKUP/rollback.sh"
