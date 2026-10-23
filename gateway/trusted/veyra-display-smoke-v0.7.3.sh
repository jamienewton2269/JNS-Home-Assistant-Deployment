#!/usr/bin/env bash
# VEYRA v0.7.3 display-only smoke test.
# Uses the known-working v0.5.1 systemd-run + Wayland + local-pipe FFplay launch pattern.
# NO ITVX capture, NO Chrome changes, NO recorder pause, NO service restart.
# Displays moving synthetic test pattern for 12 seconds and then exits.
set -Eeuo pipefail
UNIT=veyra-display-smoke-v073
SCRIPT=/opt/veyra/display-smoke-v073/smoke.sh
VUID=$(id -u veyra)
RUNTIME="/run/user/$VUID"
PULSE="unix:$RUNTIME/pulse/native"

preflight() {
  [[ $EUID -eq 0 ]] || { echo "Use sudo"; exit 2; }
  systemctl is-active --quiet veyra-kiosk.service || { echo "STOP: physical VEYRA kiosk inactive"; return 2; }
  systemctl is-active --quiet veyra-virtual-loopback-v01.service || { echo "STOP: existing capture inactive"; return 2; }
  if systemctl is-active --quiet veyra-tv-v072.service; then
    echo "STOP: v0.7.2 still active; do not overlap test sessions"; return 2
  fi
  for tool in ffplay ffmpeg systemd-run install; do
    command -v "$tool" >/dev/null || { echo "STOP: missing $tool"; return 2; }
  done
  [[ -d "$RUNTIME" ]] || { echo "STOP: VEYRA user runtime missing"; return 2; }
  local sock
  sock=$(find "$RUNTIME" -maxdepth 1 -type s -name 'wayland-*' -printf '%f\n' | sort | head -1)
  [[ -n "$sock" ]] || { echo "STOP: Wayland socket not available"; return 2; }
  echo "PASS: compositor socket $sock; original recorder not touched."
}

start() {
  preflight
  if systemctl is-active --quiet "$UNIT.service"; then
    echo "STOP: synthetic display test already active"; return 2
  fi
  local sock
  sock=$(find "$RUNTIME" -maxdepth 1 -type s -name 'wayland-*' -printf '%f\n' | sort | head -1)
  install -d -m 755 /opt/veyra/display-smoke-v073
  if [[ -e "$SCRIPT" ]] && ! cmp -s "$0" "$SCRIPT"; then
    echo "STOP: existing display test differs from downloaded source"; return 2
  fi
  install -m 755 "$0" "$SCRIPT"
  systemd-run --quiet --unit="$UNIT" --service-type=exec \
    --property=User=veyra --property=Group=veyra \
    --property=RuntimeMaxSec=20s --property=Restart=no \
    --setenv=XDG_RUNTIME_DIR="$RUNTIME" \
    --setenv=WAYLAND_DISPLAY="$sock" \
    --setenv=PULSE_SERVER="$PULSE" \
    --setenv=SDL_VIDEODRIVER=wayland \
    --setenv=SDL_AUDIODRIVER=pulseaudio \
    /usr/bin/bash "$SCRIPT" _run
  echo "DISPLAY_TEST_STARTED: 12-second moving test picture should appear on the laptop."
  echo "Recorder, Chrome, ITVX and kiosk are unchanged."
  echo "After the test, run: sudo journalctl -u $UNIT.service -n 25 --no-pager"
}

render() {
  [[ $(id -un) == veyra ]] || { echo "Run as veyra"; exit 2; }
  # Same local MPEG-TS pipe architecture as proven v0.5.1; no UDP.
  /usr/bin/ffmpeg -hide_banner -loglevel error -nostdin -re \
    -f lavfi -i 'testsrc2=size=960x540:rate=15' \
    -t 12 -an -c:v mpeg2video -q:v 6 -g 15 -bf 0 -pix_fmt yuv420p \
    -f mpegts pipe:1 | \
  /usr/bin/ffplay -hide_banner -loglevel warning -nostats \
    -fs -noborder -autoexit -an -fflags nobuffer -framedrop \
    -probesize 65536 -f mpegts -i pipe:0
}

case "${1:-}" in
  preflight) preflight ;;
  start) start ;;
  _run) render ;;
  status) systemctl status "$UNIT.service" --no-pager -l || true ;;
  stop)
    [[ $EUID -eq 0 ]] || { echo "Use sudo"; exit 2; }
    systemctl stop "$UNIT.service" 2>/dev/null || true
    echo "DISPLAY_TEST_STOPPED"
    ;;
  *) echo "Usage: sudo bash $0 {preflight|start|status|stop}"; exit 2 ;;
esac
