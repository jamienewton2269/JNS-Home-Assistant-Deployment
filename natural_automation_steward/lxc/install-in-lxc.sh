#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$ROOT_DIR/src"
REAL_SRC="$SRC/real_progress"
LIVE=/opt/natural-automation
REAL=/opt/real-progress
CONF=/etc/natural-automation
SERVICE=/etc/systemd/system/natural-automation.service

[[ $EUID -eq 0 ]] || { echo 'Run as root inside ha-steward LXC' >&2; exit 77; }

for f in "$SRC/natural_automation.py" "$SRC/steward/target.py" "$ROOT_DIR/lxc/natural-automation-lxc.service"; do
  [[ -f "$f" ]] || { echo "Missing release file: $f" >&2; exit 66; }
done

if ! id natural-automation >/dev/null 2>&1; then
  useradd --system --home-dir /var/lib/natural-automation --create-home --shell /usr/sbin/nologin natural-automation
fi

install -d -o root -g root -m 0755 "$LIVE" "$LIVE/steward" "$LIVE/tools" "$REAL"
install -d -o natural-automation -g natural-automation -m 0750 "$LIVE/data"
install -d -o root -g natural-automation -m 0750 "$CONF"

install -o root -g root -m 0755 "$SRC/natural_automation.py" "$LIVE/natural_automation.py"
install -o root -g root -m 0644 "$SRC"/steward/*.py "$LIVE/steward/"
install -o root -g root -m 0755 "$ROOT_DIR/tools/seed_repairs.py" "$LIVE/tools/seed_repairs.py"
install -o root -g root -m 0644 "$ROOT_DIR/VERSION" "$LIVE/VERSION"
install -o root -g root -m 0644 "$REAL_SRC"/*.py "$REAL/"
install -o root -g root -m 0644 "$ROOT_DIR/lxc/natural-automation-lxc.service" "$SERVICE"

python3 -m compileall -q "$LIVE" "$REAL"
chown -R natural-automation:natural-automation "$LIVE/data"

systemctl daemon-reload
systemctl enable natural-automation.service
echo LXC_INSTALL_OK
