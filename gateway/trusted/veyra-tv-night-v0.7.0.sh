#!/usr/bin/env bash
# VEYRA TV-Night v0.7.0: bounded GPU player + manually controlled advert-cover overlay.
# Provider Chrome :92, VNC, physical Cage, Home and watchlist are never restarted.
set -Eeuo pipefail
[[ $EUID == 0 ]] || { echo "Use sudo";exit 2; }
ACTION="${1:-preflight}"
BASE="https://raw.githubusercontent.com/jamienewton2269/JNS-Home-Assistant-Deployment/main/gateway/trusted"
ROOT=/opt/veyra/tv-night
PLAYERUNIT=/etc/systemd/system/veyra-tv-v070.service
COVERUNIT=/etc/systemd/system/veyra-tv-adcover-v070.service
PLAYER=veyra-tv-v070.service
COVER=veyra-tv-adcover-v070.service
CURRENT="$ROOT/current"
UI=http://127.0.0.1:8773/
preflight() {
  test -d /opt/veyra/virtual-loopback-v01 || { echo "Virtual Chrome not installed";return 2; }
  for svc in veyra-kiosk.service veyra-virtual-loopback-v01.service veyra-itvx-vnc-v01.service; do
    systemctl is-active --quiet "$svc" || { echo "SAFETY STOP: $svc is inactive";return 2; }
  done
  for c in ffmpeg ffplay python3 curl sha256sum systemctl runuser pactl; do command -v "$c" >/dev/null || { echo "Missing $c";return 2; };done
  test -c /dev/dri/renderD128 || { echo "Intel GPU unavailable";return 2; }
  for unit in "$PLAYERUNIT" "$COVERUNIT"; do
    [[ ! -f "$unit" ]] || grep -Fq '/opt/veyra/tv-night/current/' "$unit" || { echo "SAFETY STOP: conflicting unit $unit";return 2; }
  done
  for port in 8773 23570; do
    if [[ "$port" == 8773 && ! -f "$COVERUNIT" ]] &&
       ss -ltnH '( sport = :8773 )' | grep -q .; then
      echo "SAFETY STOP: port 8773 is occupied";return 2
    fi
  done
  if systemctl is-active --quiet "$PLAYER"; then
    echo 'SAFETY STOP: TV player already running. Stop before updating.';return 2
  fi
  printf 'HDMI connection: '
  cat /sys/class/drm/card0-HDMI-A-1/status 2>/dev/null || echo unknown
  echo 'Veyra Chrome, VNC, Cage intact. AV service will be started ONLY by the start command.'
}
fetch() {
  local file="$1" url="$2" dest="$3"
  curl -fL --retry 2 --connect-timeout 10 --max-time 35 "$url" -o "$dest"
  test -s "$dest"
}
install_app() {
  preflight
  install -d -m 755 -o root -g root "$ROOT"
  local stage stamp release
  stage=$(mktemp -d "$ROOT/.incoming.XXXXXXXX")
  trap 'rm -rf -- "$stage"' EXIT
  echo 'Downloading TV-night versioned components from JNS GitHub.'
  fetch player "$BASE/veyra-tv-player-v0.7.0.sh" "$stage/player.sh"
  for file in cover.py index.html app.js styles.css; do
    fetch "$file" "$BASE/veyra-tv-adcover-v070/$file" "$stage/$file"
  done
  bash -n "$stage/player.sh"
  python3 - "$stage/cover.py" <<'PY'
import ast,sys
ast.parse(open(sys.argv[1],encoding='utf-8').read())
print('PASS: overlay controller Python syntax.')
PY
  if command -v node >/dev/null; then node --check "$stage/app.js"; fi
  python3 - "$stage/cover.py" <<'PY'
import importlib.util,subprocess,sys
p=sys.argv[1]
spec=importlib.util.spec_from_file_location('cover_validation',p)
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
if not mod.FONT:
    raise SystemExit('Required font absent')
f=mod.ffplay_graph(3)
test=subprocess.run(['ffmpeg','-nostdin','-hide_banner','-loglevel','error',
  '-f','lavfi','-i',f,'-frames:v','1','-f','null','-'],
  stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,timeout=12)
if test.returncode:
    raise SystemExit('Cover frame preflight failed: '+test.stderr.decode(errors='replace')[-2000:])
print('PASS: advert cover rendered a real validation frame.')
PY
  stamp=$(date +%Y%m%d-%H%M%S)
  release="$ROOT/v070-$stamp-$$"
  install -d -m 755 -o root -g root "$release"
  for file in player.sh cover.py index.html app.js styles.css; do
    install -m 644 -o root -g root "$stage/$file" "$release/$file"
  done
  chmod 755 "$release/player.sh"
  sha256sum "$release"/*
  ln -s "$release" "$ROOT/.new.$$"
  mv -Tf "$ROOT/.new.$$" "$CURRENT"
  if [[ -f "$PLAYERUNIT" ]]; then cp -a "$PLAYERUNIT" "$PLAYERUNIT.before-$stamp"; fi
  if [[ -f "$COVERUNIT" ]]; then cp -a "$COVERUNIT" "$COVERUNIT.before-$stamp"; fi
  cat >"$PLAYERUNIT" <<'UNIT'
[Unit]
Description=Veyra TV-Night isolated four-hour shared-capture H264 trial
After=veyra-kiosk.service veyra-virtual-loopback-v01.service
Requires=veyra-virtual-loopback-v01.service

[Service]
Type=simple
ExecStart=/bin/bash /opt/veyra/tv-night/current/player.sh start
ExecStopPost=-/bin/bash /opt/veyra/tv-night/current/player.sh recover
WorkingDirectory=/opt/veyra/tv-night/current
KillMode=mixed
TimeoutStopSec=12
RuntimeMaxSec=14500
Restart=no
NoNewPrivileges=yes

[Install]
WantedBy=multi-user.target
UNIT
  cat >"$COVERUNIT" <<'UNIT'
[Unit]
Description=Veyra local manual advert cover TV controls
After=veyra-kiosk.service

[Service]
Type=simple
ExecStart=/usr/bin/python3 /opt/veyra/tv-night/current/cover.py
ExecStopPost=-/usr/bin/python3 /opt/veyra/tv-night/current/cover.py recover
WorkingDirectory=/opt/veyra/tv-night/current
Restart=on-failure
RestartSec=3
KillMode=mixed
TimeoutStopSec=5
NoNewPrivileges=yes
PrivateTmp=yes
UMask=0077
CapabilityBoundingSet=
ProtectSystem=strict
ReadWritePaths=/run /tmp
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX
[Install]
WantedBy=multi-user.target
UNIT
  chmod 644 "$PLAYERUNIT" "$COVERUNIT"
  systemctl daemon-reload
  systemctl enable --now "$COVER"
  for i in $(seq 1 24); do
    if curl -fsS --max-time 2 "$UI""api/status" >/dev/null; then
      echo 'PASS: TV remote controller is online at http://127.0.0.1:8773/'
      echo 'The TV player is NOT started yet. Run preview, then start.'
      return 0
    fi
    sleep .25
  done
  journalctl -u "$COVER" -n 30 --no-pager || true
  echo 'TV-night controller failed. No Veyra Chrome or kiosk service modified.'
  return 4
}
status() {
  echo "TV player: $(systemctl is-active "$PLAYER" 2>/dev/null || true)"
  echo "Advert cover: $(systemctl is-active "$COVER" 2>/dev/null || true)"
  for svc in veyra-kiosk.service veyra-virtual-loopback-v01.service veyra-itvx-vnc-v01.service;do
    echo "$svc: $(systemctl is-active "$svc" 2>/dev/null || true)"
  done
  echo "HDMI: $(cat /sys/class/drm/card0-HDMI-A-1/status 2>/dev/null || echo unknown)"
  echo '=== COVER ==='
  curl -fsS --max-time 3 "$UI""api/status" || true
  echo
  echo '=== SOURCE ENCODER LAST 4 LINES ==='
  journalctl -u "$PLAYER" -n 4 --no-pager || true
}
start() {
  [[ -f "$PLAYERUNIT" && -f "$COVERUNIT" ]] || { echo 'Run install first';return 2; }
  systemctl is-active --quiet "$COVER" || { echo 'Cover remote is not running; refusing TV start';return 2; }
  for svc in veyra-kiosk.service veyra-virtual-loopback-v01.service veyra-itvx-vnc-v01.service;do
    systemctl is-active --quiet "$svc" || { echo "Missing $svc";return 2; }
  done
  if systemctl is-active --quiet "$PLAYER"; then echo 'TV already running';return 0;fi
  systemctl reset-failed "$PLAYER" 2>/dev/null || true
  systemctl start --no-block "$PLAYER"
  echo 'Starting one continuous Veyra TV session for up to four hours.'
  echo 'The old recorder resumes automatically when TV session ends.'
  echo 'Use sudo bash ~/veyra-tv-night-v0.7.0.sh status for results.'
}
post(path, data) {
  local url="$1" payload="$2"
  curl -fsS --max-time 4 -H 'X-Veyra-Control: ad-cover-v070' -H 'Content-Type: application/json' \
     --data "$payload" "$UI$url"
  echo
}
stop() {
  post api/end '{}' || true
  systemctl stop "$PLAYER" || true
  bash "$CURRENT/player.sh" recover || true
  echo 'TV session ended. Original ITVX Chrome and VNC remain running.'
}
case "$ACTION" in
  preflight) preflight;;
  install) install_app;;
  preview) post api/preview '{}';;
  start) start;;
  status) status;;
  cover30) post api/start '{"seconds":30}';;
  cover60) post api/start '{"seconds":60}';;
  cover90) post api/start '{"seconds":90}';;
  cover120) post api/start '{"seconds":120}';;
  cover180) post api/start '{"seconds":180}';;
  uncover) post api/end '{}';;
  stop) stop;;
  *) echo 'Usage: sudo bash script {preflight|install|preview|start|status|cover30|cover60|cover90|cover120|cover180|uncover|stop}';exit 2;;
esac
