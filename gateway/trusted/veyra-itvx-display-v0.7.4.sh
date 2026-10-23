#!/usr/bin/env bash
# VEYRA v0.7.4: short, real ITVX virtual-display -> physical Cage smoke test.
# This is NOT the final 50fps player. It isolates the previously broken display leg.
# Preserves Chrome, ITVX profile, virtual recorder, VNC, kiosk and audio routes.
# No writing of provider media, no service restarts, no recorder SIGSTOP.
set -Eeuo pipefail

UNIT=veyra-itvx-display-v074
DEST=/opt/veyra/itvx-display-v074/player.sh
RUNTIME=/run/user/$(id -u veyra)
PULSE="unix:$RUNTIME/pulse/native"

preflight() {
  [[ $EUID -eq 0 ]] || { echo "Use sudo"; return 2; }
  for unit in veyra-kiosk.service veyra-virtual-loopback-v01.service veyra-itvx-vnc-v01.service; do
    systemctl is-active --quiet "$unit" || { echo "SAFETY STOP: $unit not active"; return 2; }
  done
  for unit in veyra-tv-v072.service veyra-tv-v070.service veyra-live-av-v051.service "$UNIT.service"; do
    if systemctl is-active --quiet "$unit"; then echo "SAFETY STOP: overlapping TV session $unit"; return 2; fi
  done
  for tool in ffmpeg ffplay systemd-run install; do
    command -v "$tool" >/dev/null || { echo "SAFETY STOP: $tool unavailable"; return 2; }
  done
  [[ -S /tmp/.X11-unix/X92 ]] || { echo "SAFETY STOP: live :92 display missing"; return 2; }
  [[ -S "$RUNTIME/pulse/native" ]] || { echo "SAFETY STOP: veyra session socket unavailable"; return 2; }
  [[ -d "$RUNTIME" ]] || { echo "SAFETY STOP: veyra runtime absent"; return 2; }
  local sock
  sock=$(find "$RUNTIME" -maxdepth 1 -type s -name 'wayland-*' -printf '%f\n' | sort | head -1)
  [[ -n "$sock" ]] || { echo "SAFETY STOP: Cage Wayland socket missing"; return 2; }
  echo "PASS: live :92 source; physical $sock compositor; all existing services preserved."
}

start() {
  preflight
  local sock
  sock=$(find "$RUNTIME" -maxdepth 1 -type s -name 'wayland-*' -printf '%f\n' | sort | head -1)
  install -d -m 755 /opt/veyra/itvx-display-v074
  # Fail closed if a different staged executable already owns our path.
  if [[ -e "$DEST" ]] && ! cmp -s "$0" "$DEST"; then
    echo "SAFETY STOP: staged script differs; inspect before replacement"; return 2
  fi
  install -m 755 "$0" "$DEST"
  systemd-run --quiet --unit="$UNIT" --service-type=exec \
    --property=User=veyra --property=Group=veyra \
    --property=RuntimeMaxSec=28s --property=Restart=no \
    --setenv=XDG_RUNTIME_DIR="$RUNTIME" \
    --setenv=WAYLAND_DISPLAY="$sock" \
    --setenv=PULSE_SERVER="$PULSE" \
    --setenv=SDL_VIDEODRIVER=wayland \
    --setenv=SDL_AUDIODRIVER=pulseaudio \
    /usr/bin/bash "$DEST" _run
  echo "LIVE_DISPLAY_TEST: showing current virtual ITVX screen on physical laptop for up to 18 seconds."
  echo "This brief test intentionally checks VIDEO ONLY; no audio routing or 30-minute buffer changes."
  echo "Check: sudo journalctl -u $UNIT.service -n 30 --no-pager"
}

render() {
  [[ $(id -un) == veyra ]] || { echo "SAFETY STOP: must run as veyra"; return 2; }
  [[ -S /tmp/.X11-unix/X92 ]] || { echo "SAFETY STOP: virtual source no longer present"; return 2; }
  # Real source, known-working v0.5.1 direct pipe. Diagnostic rate is intentionally
  # 15fps to establish a visible picture independently of the 50fps capture stage.
  /usr/bin/ffmpeg -hide_banner -loglevel warning -nostdin \
    -thread_queue_size 256 -f x11grab -framerate 15 -video_size 1366x768 -i :92.0 \
    -t 18 -map 0:v:0 -an \
    -c:v mpeg2video -pix_fmt yuv420p -q:v 7 -g 15 -bf 0 -threads 2 \
    -muxdelay 0 -muxpreload 0 -f mpegts pipe:1 | \
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
    echo "ITVX_DISPLAY_TEST_STOPPED; original services unchanged"
    ;;
  *) echo "Usage: sudo bash $0 {preflight|start|status|stop}"; exit 2 ;;
esac
