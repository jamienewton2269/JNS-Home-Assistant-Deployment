#!/usr/bin/env bash
# Veyra v0.5: bounded live A/V trial. No changes to kiosk or Chrome profiles.
set -Eeuo pipefail
UNIT=veyra-live-av-v05
SINK=veyra_virtual_capture
PROFILE=/opt/veyra/virtual-loopback-v01/profile
UIDV=$(id -u veyra)
RUNTIME=/run/user/$UIDV
PULSE=unix:$RUNTIME/pulse/native
pa() { runuser -u veyra -- env XDG_RUNTIME_DIR="$RUNTIME" PULSE_SERVER="$PULSE" pactl "$@"; }
check() {
  systemctl is-active --quiet veyra-kiosk.service || { echo 'Kiosk inactive'; exit 2; }
  systemctl is-active --quiet veyra-virtual-loopback-v01.service || { echo 'Capture inactive'; exit 2; }
  command -v ffmpeg >/dev/null; command -v ffplay >/dev/null
  pa list short sinks | awk '{print $2}' | grep -Fxq "$SINK" || { echo 'Audio sink missing'; exit 2; }
  [[ -S "$RUNTIME/pulse/native" ]] || { echo 'Pulse socket absent'; exit 2; }
  find "$RUNTIME" -maxdepth 1 -type s -name 'wayland-*' | grep -q . || { echo 'Wayland socket absent'; exit 2; }
  echo 'PASS: kiosk, capture and virtual audio sink present'
}
route() {
  local n=0 id pid
  while read -r id pid; do
    [[ "$id" =~ ^[0-9]+$ && "$pid" =~ ^[0-9]+$ ]] || continue
    [[ -r /proc/$pid/cmdline ]] || continue
    if tr '\0' '\n' < "/proc/$pid/cmdline" | grep -Fxq -- "--user-data-dir=$PROFILE"; then
      pa move-sink-input "$id" "$SINK"
      pa set-sink-input-mute "$id" 0
      echo "Verified virtual Chrome stream $id -> $SINK"
      n=$((n+1))
    fi
  done < <(pa list sink-inputs | awk '/^Sink Input #[0-9]+/ { id=$3; sub(/^#/,"",id) } /application.process.id =/ { pid=$3; gsub(/"/,"",pid); if (id!="") print id,pid }')
  if (( n == 0 )); then echo 'No virtual Chrome audio stream: resume ITVX programme in VNC before start'; return 3; fi
}
start() {
  check
  route
  if systemctl is-active --quiet "$UNIT.service"; then echo 'Already active'; exit 0; fi
  sock=$(find "$RUNTIME" -maxdepth 1 -type s -name 'wayland-*' -printf '%f\n' | sort | head -1)
  script=$(readlink -f "$0")
  systemd-run --quiet --unit="$UNIT" --service-type=exec --property=User=veyra --property=Group=veyra --property=RuntimeMaxSec=100s --property=Restart=no --setenv=XDG_RUNTIME_DIR="$RUNTIME" --setenv=WAYLAND_DISPLAY="$sock" --setenv=PULSE_SERVER="$PULSE" --setenv=SDL_VIDEODRIVER=wayland --setenv=SDL_AUDIODRIVER=pulseaudio /usr/bin/bash "$script" _run
  echo "Live playback test started for up to 90 seconds."
  echo "Emergency stop: sudo bash $script stop"
}
run() {
  [[ $(id -un) == veyra ]] || exit 2
  set -o pipefail
  ffmpeg -hide_banner -loglevel warning -nostdin -thread_queue_size 256 -f x11grab -framerate 15 -video_size 1366x768 -i :92.0 -thread_queue_size 512 -f pulse -sample_rate 48000 -channels 2 -i "$SINK.monitor" -t 90 -map 0:v:0 -map 1:a:0 -c:v mpeg2video -q:v 7 -g 15 -bf 0 -threads 2 -c:a mp2 -b:a 160k -ar 48000 -ac 2 -muxdelay 0 -muxpreload 0 -f mpegts pipe:1 |
  ffplay -hide_banner -loglevel warning -nostats -fs -noborder -autoexit -fflags nobuffer -framedrop -sync audio -probesize 65536 -f mpegts -i pipe:0
}
if (( $# != 1 )); then echo 'Usage: sudo bash script {preflight|start|stop|status|logs}'; exit 2; fi
case "$1" in
  preflight) [[ $EUID == 0 ]] || exit 2; check ;;
  start) [[ $EUID == 0 ]] || exit 2; start ;;
  stop) [[ $EUID == 0 ]] || exit 2; systemctl stop "$UNIT.service" 2>/dev/null || true; echo 'Live test stopped' ;;
  status) systemctl status "$UNIT.service" --no-pager -l || true ;;
  logs) journalctl -u "$UNIT.service" -n 60 --no-pager ;;
  _run) run ;;
  *) echo 'Unknown command'; exit 2 ;;
esac
