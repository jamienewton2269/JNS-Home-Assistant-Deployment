#!/usr/bin/env bash
# Veyra live A/V v0.5.2: 25fps UK video and modest decoder buffering; preserves v0.5.1.
# Safe bounded trial: leaves existing kiosk, provider profiles and recorder unchanged.
set -Eeuo pipefail

UNIT=veyra-live-av-v052
SINK=veyra_virtual_capture
PROFILE=/opt/veyra/virtual-loopback-v01/profile
VUID=$(id -u veyra)
RUNTIME=/run/user/$VUID
PULSE=unix:$RUNTIME/pulse/native
SCRIPT=$(readlink -f "$0")

pa() {
  if [[ $(id -un) == veyra ]]; then
    env XDG_RUNTIME_DIR="$RUNTIME" PULSE_SERVER="$PULSE" pactl "$@"
  else
    runuser -u veyra -- env XDG_RUNTIME_DIR="$RUNTIME" PULSE_SERVER="$PULSE" pactl "$@"
  fi
}
preflight() {
  systemctl is-active --quiet veyra-kiosk.service || { echo 'Physical kiosk not active'; return 2; }
  systemctl is-active --quiet veyra-virtual-loopback-v01.service || { echo 'Virtual capture not active'; return 2; }
  command -v ffmpeg >/dev/null
  command -v ffplay >/dev/null
  [[ -S "$RUNTIME/pulse/native" ]] || { echo 'PipeWire/Pulse socket unavailable'; return 2; }
  pa list short sinks | awk '{print $2}' | grep -Fxq "$SINK" || { echo 'Virtual audio sink missing'; return 2; }
  find "$RUNTIME" -maxdepth 1 -type s -name 'wayland-*' | grep -q . || { echo 'Wayland compositor socket missing'; return 2; }
  echo 'PASS: physical kiosk, virtual capture, PipeWire sink and Wayland socket available'
}
route_audio() {
  local id pid count=0
  while read -r id pid; do
    [[ "$id" =~ ^[0-9]+$ && "$pid" =~ ^[0-9]+$ && -r "/proc/$pid/cmdline" ]] || continue
    # Validate the exact virtual Chrome profile, never route the physical GUI Chrome.
    if tr '\0' '\n' < "/proc/$pid/cmdline" | grep -Fxq -- "--user-data-dir=$PROFILE"; then
      pa move-sink-input "$id" "$SINK"
      pa set-sink-input-mute "$id" 0
      echo "Routed virtual Chrome audio stream $id (PID $pid)"
      count=$((count+1))
    fi
  done < <(pa list sink-inputs | awk '
    /^Sink Input #[0-9]+/ { id=$3; sub(/^#/,"",id) }
    /application.process.id =/ { pid=$3; gsub(/"/,"",pid); if(id!="") print id,pid }
  ')
  if (( count == 0 )); then
    echo 'No active virtual Chrome audio stream: video will start; audio remains silent until available.'
  fi
}
start() {
  preflight
  if systemctl is-active --quiet veyra-live-av-v051.service; then echo "Stop the previous 15fps trial before starting the new one"; return 2; fi
  if systemctl is-active --quiet "$UNIT.service"; then echo 'Live player already running'; return; fi
  route_audio
  local sock
  sock=$(find "$RUNTIME" -maxdepth 1 -type s -name 'wayland-*' -printf '%f\n' | sort | head -1)
  systemd-run --quiet --collect --unit="$UNIT" --service-type=exec \
    --property=User=veyra --property=Group=veyra \
    --property=RuntimeMaxSec=110s --property=Restart=no \
    --setenv=XDG_RUNTIME_DIR="$RUNTIME" \
    --setenv=WAYLAND_DISPLAY="$sock" \
    --setenv=PULSE_SERVER="$PULSE" \
    --setenv=SDL_VIDEODRIVER=wayland \
    --setenv=SDL_AUDIODRIVER=pulseaudio \
    /usr/bin/bash "$SCRIPT" _run
  echo 'STARTED: up to 90 seconds of 25fps live ITVX on Veyra screen; fps/speed visible in logs.'
  echo "Emergency stop: sudo bash $SCRIPT stop"
}
run() {
  [[ $(id -un) == veyra ]] || { echo 'Must run under veyra'; exit 2; }
  # Pick up Chrome audio if it starts later; routing is limited to the virtual profile.
  (while true; do route_audio >/dev/null 2>&1 || true; sleep 3; done) &
  local watcher=$!
  trap 'kill "$watcher" 2>/dev/null || true' EXIT
  set -o pipefail
  /usr/bin/ffmpeg -hide_banner -loglevel info -stats_period 5 -stats -benchmark -nostdin \
    -thread_queue_size 256 -f x11grab -framerate 25 -video_size 1366x768 -i :92.0 \
    -thread_queue_size 512 -f pulse -sample_rate 48000 -channels 2 -i "$SINK.monitor" \
    -t 90 -map 0:v:0 -map 1:a:0 \
    -c:v mpeg2video -pix_fmt yuv420p -q:v 7 -g 25 -bf 0 -threads 2 \
    -c:a mp2 -b:a 160k -ar 48000 -ac 2 \
    -muxdelay 0 -muxpreload 0 -f mpegts pipe:1 |
  /usr/bin/ffplay -hide_banner -loglevel warning -nostats \
    -fs -noborder -autoexit -framedrop -sync audio \
    -probesize 65536 -f mpegts -i pipe:0
}
case "$(printf '%s' "$*")" in
  preflight) [[ $EUID == 0 ]] || exit 2; preflight ;;
  start) [[ $EUID == 0 ]] || exit 2; start ;;
  stop) [[ $EUID == 0 ]] || exit 2; systemctl stop "$UNIT.service" 2>/dev/null || true; echo 'Live player stopped; Veyra Home visible' ;;
  status) systemctl status "$UNIT.service" --no-pager -l || true ;;
  logs) journalctl -u "$UNIT.service" -n 60 --no-pager ;;
  _run) run ;;
  *) echo "Usage: sudo bash $SCRIPT {preflight|start|stop|status|logs}"; exit 2 ;;
esac
