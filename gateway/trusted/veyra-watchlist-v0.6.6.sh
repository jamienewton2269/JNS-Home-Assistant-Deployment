#!/usr/bin/env bash
# VEYRA watchlist beta v0.6.6 — transactional, separate localhost service.
# NEVER restarts/patches Cage, Chrome, ITVX, VNC, or Veyra Home service.
# The watchlist database survives upgrade and rollback.
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || { echo "Please run with sudo.";exit 2; }
CMD="${1:-preflight}"
ROOT=/opt/veyra/watchlist
DBROOT=/var/lib/veyra/watchlist
SERVICE=veyra-watchlist.service
UNIT=/etc/systemd/system/$SERVICE
BASE=https://raw.githubusercontent.com/jamienewton2269/JNS-Home-Assistant-Deployment/main/gateway/trusted/veyra-watchlist-v066
preflight() {
  test -d /opt/veyra/veyra || { echo "Veyra installation not found";return 2; }
  id veyra >/dev/null
  command -v curl >/dev/null
  command -v python3 >/dev/null
  command -v systemctl >/dev/null
  if [[ -f "$UNIT" ]] && ! grep -Fq /opt/veyra/watchlist/current/server.py "$UNIT"; then
    echo "SAFETY STOP: unrelated unit already uses $SERVICE";return 2
  fi
  if [[ ! -f "$UNIT" ]] && ss -ltnH '( sport = :8772 )' | grep -q .; then
    echo "SAFETY STOP: port 8772 is already in use";return 2
  fi
  echo "PASS: Veyra installed and local watchlist service can be deployed independently."
  echo "Provider session: untouched. Physical kiosk: untouched. Database: never deleted by this installer."
}
health() {
  printf 'Watchlist: '
  curl -fsS --max-time 3 http://127.0.0.1:8772/api/health || return 1
  echo
}
install_app() {
  preflight
  local stage release previous oldunit stamped
  install -d -o root -g root -m 755 "$ROOT"
  install -d -o veyra -g veyra -m 700 "$DBROOT"
  stage=$(mktemp -d "$ROOT/.staging.XXXXXXXX")
  trap 'rm -rf -- "$stage"' EXIT
  echo 'Fetching versioned backend and interface from JNS GitHub...'
  for file in server.py index.html app.css app.js selftest.py; do
    curl -fLsS --retry 2 --connect-timeout 10 --max-time 30 \
      "$BASE/$file" -o "$stage/$file"
    test -s "$stage/$file"
  done
  python3 - "$stage/server.py" <<'PY'
import ast,sys
ast.parse(open(sys.argv[1],encoding='utf-8').read(),filename=sys.argv[1])
print('PASS: watchlist backend Python syntax')
PY
  if command -v node >/dev/null; then
    node --check "$stage/app.js"
    echo 'PASS: watchlist client JavaScript syntax'
  else
    echo 'INFO: Node.js unavailable; browser JavaScript syntax check deferred.'
  fi
  echo 'Running isolated API/database smoke tests before service activation...'
  python3 "$stage/selftest.py" "$stage"
  grep -Fq 'VEYRA' "$stage/index.html" || { echo 'Missing watchlist UI marker';return 3; }
  grep -Fq '127.0.0.1' "$stage/server.py" || { echo 'Backend must be localhost-only';return 3; }
  stamped=$(date +%Y%m%d-%H%M%S)
  release="$ROOT/v066-$stamped-$$"
  install -d -o root -g root -m 755 "$release"
  for file in server.py index.html app.css app.js selftest.py; do
    install -o root -g root -m 644 "$stage/$file" "$release/$file"
  done
  echo '=== New immutable source hashes ==='
  sha256sum "$release/"*
  previous=$(readlink "$ROOT/current" 2>/dev/null || true)
  oldunit=''
  if [[ -f "$UNIT" ]]; then
    oldunit="$UNIT.before-v066-$stamped"
    cp -a "$UNIT" "$oldunit"
  fi
  ln -s "$release" "$ROOT/.next.$$"
  mv -Tf "$ROOT/.next.$$" "$ROOT/current"
  cat >"$UNIT" <<'UNITFILE'
[Unit]
Description=Veyra local watchlist beta (SQLite, loopback only)
After=network.target

[Service]
Type=simple
User=veyra
Group=veyra
WorkingDirectory=/opt/veyra/watchlist/current
Environment=PYTHONDONTWRITEBYTECODE=1
Environment=VEYRA_WATCHLIST_DB=/var/lib/veyra/watchlist/watchlist.sqlite3
ExecStart=/usr/bin/python3 /opt/veyra/watchlist/current/server.py
Restart=on-failure
RestartSec=2
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=/var/lib/veyra/watchlist
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX
CapabilityBoundingSet=
LockPersonality=yes
UMask=0077

[Install]
WantedBy=multi-user.target
UNITFILE
  chmod 644 "$UNIT"
  systemctl daemon-reload
  if systemctl is-active --quiet "$SERVICE"; then
    systemctl restart "$SERVICE"
  else
    systemctl enable --now "$SERVICE"
  fi
  for i in $(seq 1 20); do
    if health; then
      echo "PASS: watchlist is live at http://127.0.0.1:8772/"
      echo 'PROGRAMME PROFILE AND KIOSK LEFT UNCHANGED.'
      echo "Versioned source: $release"
      echo "Previous source: ${previous:-none}"
      echo "Previous systemd unit: ${oldunit:-none}"
      return 0
    fi
    sleep .25
  done
  echo 'WATCHLIST SERVICE FAILED TO START — original Cage/Chrome not altered.'
  journalctl -u "$SERVICE" -n 20 --no-pager || true
  echo "Source currently at $release; previous source ${previous:-none}"
  return 5
}
status() {
  echo "Watchlist service: $(systemctl is-active "$SERVICE" 2>/dev/null || true)"
  health || true
  echo "Database retained at $DBROOT/watchlist.sqlite3"
  for n in veyra-kiosk.service veyra-virtual-loopback-v01.service veyra-itvx-vnc-v01.service; do
    echo "$n: $(systemctl is-active "$n" 2>/dev/null || true)"
  done
}
rollback() {
  if [[ -f "$UNIT" ]] && grep -Fq /opt/veyra/watchlist/current/server.py "$UNIT"; then
    systemctl disable --now "$SERVICE" || true
    echo 'Watchlist beta stopped. No Veyra multimedia services changed.'
    echo "All local database records retained: $DBROOT/watchlist.sqlite3"
  else
    echo 'Watchlist service not installed by this script; nothing to roll back.'
  fi
}
case "$CMD" in
  preflight) preflight;;
  install) install_app;;
  status) status;;
  rollback) rollback;;
  *) echo 'Usage: sudo bash veyra-watchlist-v0.6.6.sh {preflight|install|status|rollback}';exit 2;;
esac
