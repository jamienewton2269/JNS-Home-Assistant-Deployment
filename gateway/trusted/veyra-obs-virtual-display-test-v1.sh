#!/usr/bin/env bash
# Veyra virtual-display / OBS protected-playback compatibility experiment.
# TEST ONLY. Does not touch Cage, Sway, systemd kiosk, real display or provider profiles.
set -Eeuo pipefail
# DEPRECATED: this pre-existing experiment attempts to create Xvfb :92.
# :92 is now the LIVE ITVX Chrome display. Never run start/install here.
CMD="${1:-}"
if [[ "$CMD" == start || "$CMD" == install ]]; then
  echo "SAFETY STOP: obsolete OBS experiment conflicts with live ITVX Xvfb :92; use veyra-obs-backend-v1.sh instead." >&2
  exit 2
fi
BASE=/home/jnsadmin/veyra-obs-test
DISPLAY_NUM=:92
need(){ command -v "$1" >/dev/null || { echo "Missing $1"; exit 2; }; }
if [ "$CMD" = install ]; then
 [ "$(id -u)" = 0 ] || { echo 'Run install with sudo'; exit 2; }
 apt-get update
 DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends xvfb openbox obs-studio ffmpeg python3-venv curl x11-utils dbus-x11
 install -d -o jnsadmin -g jnsadmin -m 700 "$BASE"
 echo 'Veyra OBS virtual display dependencies installed; kiosk untouched.'
 exit 0
fi
[ "$(id -un)" = jnsadmin ] || { echo 'Run start/status/stop as jnsadmin (without sudo)'; exit 2; }
mkdir -p "$BASE"
case "$CMD" in
 start)
  need Xvfb; need openbox; need obs; need ffprobe
  if [ -f "$BASE/pids" ]; then echo 'Existing test; run stop first'; exit 3; fi
  /usr/bin/Xvfb "$DISPLAY_NUM" -screen 0 1280x720x24 -nolisten tcp -ac >"$BASE/xvfb.log" 2>&1 &
  xv=$!
  sleep 2
  kill -0 "$xv" || { echo 'Xvfb failed'; exit 4; }
  export DISPLAY="$DISPLAY_NUM"
  /usr/bin/openbox --sm-disable >"$BASE/openbox.log" 2>&1 &
  ob=$!
  CHROME=/opt/veyra/vendor/google-chrome/google-chrome
  [ -x "$CHROME" ] || CHROME=/usr/bin/google-chrome
  [ -x "$CHROME" ] || { echo 'Chrome not found'; kill "$ob" "$xv" 2>/dev/null || :; exit 5; }
  URL="${2:-https://www.itv.com/watch}"
  case "$URL" in https://*) ;; *) echo 'Only HTTPS provider URLs accepted'; exit 6;; esac
  mkdir -p "$BASE/chrome-profile"
  "$CHROME" --ozone-platform=x11 --user-data-dir="$BASE/chrome-profile" --no-first-run --window-size=1280,720 "$URL" >"$BASE/chrome.log" 2>&1 &
  ch=$!
  # OBS starts on same virtual X11 display. Set up Screen Capture (XSHM), not a network stream.
  mkdir -p "$BASE/obs-config"
  obs --portable --disable-updater --minimize-to-tray >"$BASE/obs.log" 2>&1 &
  os=$!
  printf '%s\n' "$xv" "$ob" "$ch" "$os" > "$BASE/pids"
  echo 'Virtual browser and OBS launched on :92 without altering the physical display.'
  echo 'OBS requires Screen Capture (XSHM) source configuration and recording to assess captured frames.'
  echo 'Test provider DRM playback only through its normal login/CDM. No DRM bypass or copy-protection override.'
  echo "Logs: $BASE; virtual display: $DISPLAY_NUM"
  ;;
 status)
  [ -f "$BASE/pids" ] && while read -r p; do ps -p "$p" -o pid,comm,args --no-headers || :; done < "$BASE/pids"
  [ -f "$BASE/obs.log" ] && tail -n 15 "$BASE/obs.log" || :
  ;;
 stop)
  if [ -f "$BASE/pids" ]; then
    while read -r p; do kill -TERM "$p" 2>/dev/null || :; done < "$BASE/pids"
    rm -f "$BASE/pids"
    echo 'Isolated test processes stopped.'
  fi
  ;;
 *) echo 'Usage: sudo bash script install | bash script start [https://provider.url] | bash script status | bash script stop'; exit 2;;
esac
