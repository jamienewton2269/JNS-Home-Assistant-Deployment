#!/usr/bin/env bash
# Veyra v0.5.6 one-encode A/V + rolling buffer trial.
# Does not restart virtual Chrome, VNC, Cage or change browser settings.
# Normal recorder FFmpeg only is SIGSTOPped for this test; independent timer restores it.
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || { echo "Use sudo"; exit 2; }
CAP=veyra-virtual-loopback-v01.service
VNC=veyra-itvx-vnc-v01.service
SINK=veyra_virtual_capture
PORT=23560
ROOT=/opt/veyra/virtual-loopback-v01
BASE="$ROOT/shared-test-v056"
VUID=$(id -u veyra)
RUNTIME="/run/user/$VUID"
PULSE="unix:$RUNTIME/pulse/native"
DURATION=75
paused=0
encpid=''
playerpid=''
failsafe=''
ffpid=''
cg=''
pa() { runuser -u veyra -- env XDG_RUNTIME_DIR="$RUNTIME" PULSE_SERVER="$PULSE" pactl "$@"; }
cleanup() {
  rc=$?
  trap - EXIT INT TERM
  set +e
  for id in "$playerpid" "$encpid"; do
    if [[ "$id" =~ ^[0-9]+$ ]]; then
      kill -TERM -- "-$id" 2>/dev/null || true
    fi
  done
  sleep 0.3
  for id in "$playerpid" "$encpid"; do
    if [[ "$id" =~ ^[0-9]+$ ]]; then
      kill -KILL -- "-$id" 2>/dev/null || true
      wait "$id" 2>/dev/null || true
    fi
  done
  if [[ "$ffpid" =~ ^[0-9]+$ ]]; then
    kill -CONT "$ffpid" 2>/dev/null || true
    if (( paused )); then echo "RESTORED: original recording process resumed"; fi
  fi
  if [[ -n "$failsafe" ]]; then systemctl stop "$failsafe.timer" 2>/dev/null || true; fi
  # Only remove segments in this isolated temporary trial folder.
  if [[ -d "$BASE/segments" ]]; then
    find "$BASE/segments" -maxdepth 1 -type f -name 'segment??.ts' -delete
  fi
  if (( rc != 0 )); then
    echo "Trial stopped with status $rc"
    [[ -f "$BASE/encoder.log" ]] && tail -35 "$BASE/encoder.log"
    [[ -f "$BASE/player.log" ]] && tail -20 "$BASE/player.log"
  fi
  exit "$rc"
}
preflight() {
  for u in "$CAP" "$VNC" veyra-kiosk.service; do
    systemctl is-active --quiet "$u" || { echo "SAFETY STOP: $u inactive"; return 2; }
  done
  for u in veyra-live-av-v051.service veyra-live-av-v052.service; do
    ! systemctl is-active --quiet "$u" || { echo "SAFETY STOP: old player $u active"; return 2; }
  done
  command -v ffmpeg >/dev/null
  command -v ffplay >/dev/null
  command -v setsid >/dev/null
  [[ -S /tmp/.X11-unix/X92 ]] || { echo 'Virtual display unavailable'; return 2; }
  [[ -S "$RUNTIME/pulse/native" ]] || { echo 'Pulse/PipeWire server unavailable'; return 2; }
  pa list short sinks | awk '{print $2}' | grep -Fxq "$SINK" || { echo 'Virtual audio sink missing'; return 2; }
  physical=$(pa list short sinks | awk -v virtual="$SINK" '$2!=virtual && $2~/^alsa_output/ {print $2}')
  [[ "$(printf '%s\n' "$physical" | grep -c . || true)" == 1 ]] || { echo 'Expected exactly one ALSA speaker sink; aborting'; return 2; }
  sock=$(find "$RUNTIME" -maxdepth 1 -type s -name 'wayland-*' -printf '%f\n' | sort | head -1)
  [[ -n "$sock" ]] || { echo 'No Wayland socket'; return 2; }
  if ss -lunH | awk '{print $5}' | grep -Eq ":$PORT$"; then echo "UDP $PORT already in use"; return 2; fi
  cg=$(systemctl show -p ControlGroup --value "$CAP")
  [[ -n "$cg" && -d "/sys/fs/cgroup$cg" ]] || { echo 'Capture cgroup missing'; return 2; }
  mapfile -t rec < <(
    find "/sys/fs/cgroup$cg" -name cgroup.procs -exec cat {} + |
    sort -un |
    while read -r pid; do
      [[ -r "/proc/$pid/comm" ]] || continue
      read -r cmd < "/proc/$pid/comm" || true
      [[ "$cmd" == ffmpeg ]] && echo "$pid"
    done
  )
  (( ${#rec[@]} == 1 )) || { echo "Expected one recorder FFmpeg, got ${#rec[@]}"; return 2; }
  ffpid=${rec[0]}
  cmdline=$(tr '\0' ' ' < "/proc/$ffpid/cmdline")
  [[ "$cmdline" == *x11grab* && "$cmdline" == *:92* ]] || { echo "Wrong recorder process $ffpid"; return 2; }
  echo "PASS: kiosk, VNC and virtual Chrome running; recorder PID $ffpid; 25fps/75-second trial"
}
route() {
  local id pid
  while read -r id pid; do
    [[ "$id" =~ ^[0-9]+$ && "$pid" =~ ^[0-9]+$ && -r "/proc/$pid/cmdline" ]] || continue
    if tr '\0' '\n' < "/proc/$pid/cmdline" | grep -Fxq -- "--user-data-dir=$ROOT/profile"; then
      pa move-sink-input "$id" "$SINK" 2>/dev/null || true
      pa set-sink-input-mute "$id" 0 2>/dev/null || true
    fi
  done < <(pa list sink-inputs | awk '
     /^Sink Input #[0-9]+/ {id=$3;sub(/^#/,"",id)}
     /application.process.id =/ {pid=$3;gsub(/"/,"",pid);if(id!="")print id,pid}
  ')
}
run() {
  preflight
  trap cleanup EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  mkdir -p "$BASE/segments"
  chown veyra:veyra "$BASE" "$BASE/segments"
  find "$BASE/segments" -maxdepth 1 -type f -name 'segment??.ts' -delete
  : >"$BASE/encoder.log"; : >"$BASE/player.log"
  chown veyra:veyra "$BASE/encoder.log" "$BASE/player.log"
  route
  failsafe="veyra-v056-resume-$(date +%s)-$$"
  # Independent timer validates PID still belongs to recorder before resuming.
  systemd-run --quiet --collect --unit="$failsafe" --on-active=95s \
    /usr/bin/bash -c 'p="$1"; c="$2"; if [[ -r "/proc/$p/cmdline" ]] && tr "\0" " " < "/proc/$p/cmdline" | grep -Fq "x11grab" && grep -Fq "$c" "/proc/$p/cgroup"; then kill -CONT "$p"; fi' \
    _ "$ffpid" "$cg"
  kill -STOP "$ffpid"
  paused=1
  echo "Paused ONLY the previous recorder FFmpeg; original Chrome and VNC remain running."
  local output
  output="[f=mpegts:onfail=abort]udp://127.0.0.1:$PORT?pkt_size=1316|[f=segment:segment_time=4:segment_wrap=10:segment_format=mpegts:reset_timestamps=1]$BASE/segments/segment%02d.ts"
  setsid runuser -u veyra -- env DISPLAY=:92 XDG_RUNTIME_DIR="$RUNTIME" PULSE_SERVER="$PULSE" \
    /usr/bin/ffmpeg -hide_banner -loglevel info -stats_period 5 -stats -nostdin \
    -thread_queue_size 256 -f x11grab -framerate 25 -video_size 1366x768 -i :92.0 \
    -thread_queue_size 512 -f pulse -sample_rate 48000 -channels 2 -i "$SINK.monitor" \
    -t "$DURATION" -map 0:v:0 -map 1:a:0 \
    -c:v mpeg2video -pix_fmt yuv420p -q:v 7 -g 25 -bf 0 -threads 2 \
    -c:a mp2 -b:a 160k -ar 48000 -ac 2 \
    -muxdelay 0 -muxpreload 0 -f tee "$output" \
    >"$BASE/encoder.log" 2>&1 &
  encpid=$!
  sleep 3
  kill -0 "$encpid" 2>/dev/null || { echo "Encoder quit early"; return 5; }
  echo "One FFmpeg capture now serves both the ring segments and the physical output."
  setsid runuser -u veyra -- env XDG_RUNTIME_DIR="$RUNTIME" \
    WAYLAND_DISPLAY="$sock" PULSE_SERVER="$PULSE" PULSE_SINK="$physical" \
    SDL_VIDEODRIVER=wayland SDL_AUDIODRIVER=pulseaudio \
    /usr/bin/ffplay -hide_banner -loglevel warning -nostats -fs -noborder \
    -framedrop -sync audio -probesize 65536 \
    -i "udp://127.0.0.1:$PORT?fifo_size=1000000&overrun_nonfatal=1" \
    >"$BASE/player.log" 2>&1 &
  playerpid=$!
  echo "Playing for approximately $DURATION seconds; use Ctrl+C to stop safely."
  set +e
  wait "$encpid"
  local code=$?
  set -e
  if (( code )); then echo "Shared encoder stopped unexpectedly: exit $code"; return "$code"; fi
  echo "SHARED ENCODER COMPLETE:"
  grep -E 'frame=.*fps=.*speed=' "$BASE/encoder.log" | tail -3 || true
  echo "The test recorded temporary ring segments while displaying the same encoded stream."
  echo "Temporary media will be deleted and the original recorder resumed by cleanup."
}
case "${1:-}" in
  preflight) preflight ;;
  start) run ;;
  status)
    for u in "$CAP" "$VNC" veyra-kiosk.service; do echo "$u: $(systemctl is-active "$u" 2>/dev/null || true)"; done
    ;;
  *) echo "Usage: sudo bash $0 {preflight|start|status}"; exit 2 ;;
esac
