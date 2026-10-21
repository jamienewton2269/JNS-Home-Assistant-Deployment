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
LIVE=/opt/natural-automation
REAL=/opt/real-progress
RELEASES=/opt/.natural-automation-releases
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP="$RELEASES/v1-pre-$STAMP"

for required in   "$SRC/natural_automation.py"   "$SRC/steward/store.py"   "$SRC/steward/writer.py"   "$SRC/steward/target.py"   "$SRC/steward/proposals.py"   "$SERVICE"   "$TOOLS/seed_repairs.py"
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

mkdir -p "$LIVE/steward" "$LIVE/tools" "$REAL"
install -m 0755 "$SRC/natural_automation.py" "$LIVE/natural_automation.py"
find "$LIVE/steward" -maxdepth 1 -type f -name '*.py' -delete
install -m 0644 "$SRC"/steward/*.py "$LIVE/steward/"
install -m 0755 "$TOOLS/seed_repairs.py" "$LIVE/tools/seed_repairs.py"

find "$REAL" -maxdepth 1 -type f -name '*.py' -delete
install -m 0644 "$SRC"/real_progress/*.py "$REAL/"

install -m 0644 "$SERVICE" /etc/systemd/system/natural-automation.service

python3 -m compileall -q "$LIVE" "$REAL"

if [[ -n "$SEED_JSON" ]]; then
  [[ -f "$SEED_JSON" ]] || { echo "Seed file missing: $SEED_JSON" >&2; exit 66; }
  python3 "$LIVE/tools/seed_repairs.py"     --db "$LIVE/data/steward.db"     --import-json "$SEED_JSON"
fi

cat > "$BACKUP/rollback.sh" <<EOF
#!/usr/bin/env bash
set -Eeuo pipefail
systemctl stop natural-automation.service || true
if [[ -f "$BACKUP/natural_automation.py" ]]; then
  cp -a "$BACKUP/natural_automation.py" "$LIVE/natural_automation.py"
fi
if [[ -d "$BACKUP/steward" ]]; then
  rm -rf "$LIVE/steward"
  cp -a "$BACKUP/steward" "$LIVE/steward"
fi
if [[ -d "$BACKUP/real-progress" ]]; then
  rm -rf "$REAL"
  cp -a "$BACKUP/real-progress" "$REAL"
fi
if [[ -f "$BACKUP/natural-automation.service" ]]; then
  cp -a "$BACKUP/natural-automation.service" /etc/systemd/system/natural-automation.service
fi
if [[ -f "$BACKUP/steward.db" ]]; then
  cp -a "$BACKUP/steward.db" "$LIVE/data/steward.db"
fi
systemctl daemon-reload
systemctl restart natural-automation.service
EOF
chmod 0750 "$BACKUP/rollback.sh"

systemctl daemon-reload
systemctl restart natural-automation.service
sleep 2
systemctl is-active --quiet natural-automation.service

echo "INSTALL_OK"
echo "backup=$BACKUP"
echo "rollback=$BACKUP/rollback.sh"
