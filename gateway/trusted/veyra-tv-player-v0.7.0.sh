#!/usr/bin/env bash
# Veyra v0.7.0: TV-night iHD A/V shared-capture viewer, four-hour bounded pilot.
# No global graphics driver changes. Synthetic encoder check BEFORE recorder pause.
# Does not restart virtual Chrome, VNC, Cage or change browser settings.
# Normal recorder FFmpeg only is SIGSTOPped for this test; independent timer restores it.
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || { echo "Use sudo"; exit 2; }
CAP=veyra-virtual-loopback-v01.service
VNC=veyra-itvx-vnc-v01.service
SINK=veyra_virtual_capture
PORT=23570
ROOT=/opt/veyra/virtual-loopback-v01
BASE="$ROOT/shared-test-v070"
VUID=$(id -u veyra)
RUNTIME="/run/user/$VUID"
PULSE="unix:$RUNTIME/pulse/native"
DURATION=14400
paused=0
encpid=''
playerpid=''
failsafe=''
ffpid=''
cg=''
ihd_tmp=''
ihd_dir=''
ihd_libs=''
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
  if [[ -n "$ihd_tmp" && -d "$ihd_tmp" ]]; then rm -rf -- "$ihd_tmp"; fi
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
  systemctl is-active --quiet veyra-tv-v070.service && [[ "${INVOCATION_ID:-}" == "" ]] && {
    echo 'SAFETY STOP: TV-night player is already running';return 2;
  }
  for u in "$CAP" "$VNC" veyra-kiosk.service; do
    systemctl is-active --quiet "$u" || { echo "SAFETY STOP: $u inactive"; return 2; }
  done
  for u in veyra-live-av-v051.service veyra-live-av-v052.service; do
    ! systemctl is-active --quiet "$u" || { echo "SAFETY STOP: old player $u active"; return 2; }
  done
  command -v ffmpeg >/dev/null
  command -v ffplay >/dev/null
  command -v setsid >/dev/null
  for cmd in vainfo apt-get dpkg-deb ldd; do command -v "$cmd" >/dev/null; done
  [[ -c /dev/dri/renderD128 ]] || { echo "Intel GPU render node unavailable"; return 2; }
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
  echo "PASS: kiosk, VNC and Chrome running; recorder PID $ffpid; bounded 4-hour GPU playback."
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
stage_ihd() {
  local name deb candidate pkg
  candidate=$(apt-cache policy intel-media-va-driver | sed -n 's/^  Candidate: //p' | head -1)
  [[ -n "$candidate" && "$candidate" != "(none)" ]] || {
    echo "SAFETY STOP: no iHD driver in configured Debian sources"; return 2;
  }
  ihd_tmp=$(mktemp -d /tmp/veyra-ihd-v070.XXXXXXXX)
  chmod 755 "$ihd_tmp"
  mkdir -m 755 "$ihd_tmp/extract"
  for name in intel-media-va-driver libigdgmm12; do
    echo "Staging $name (no package installation)"
    ( cd "$ihd_tmp" && apt-get -qq download "$name" ) || return 3
    deb=$(find "$ihd_tmp" -maxdepth 1 -type f -name "${name}_*.deb" -print -quit)
    [[ -n "$deb" ]] || { echo "Missing downloaded $name"; return 3; }
    pkg=$(dpkg-deb --field "$deb" Package)
    [[ "$pkg" == "$name" ]] || { echo "Package validation failed"; return 3; }
    dpkg-deb -x "$deb" "$ihd_tmp/extract" || return 3
  done
  ihd_dir=$(find "$ihd_tmp/extract" -name iHD_drv_video.so -type f -print -quit)
  [[ -n "$ihd_dir" ]] || { echo "Missing iHD driver library"; return 3; }
  ihd_dir=$(dirname "$ihd_dir")
  ihd_libs="$ihd_tmp/extract/usr/lib/x86_64-linux-gnu"
  chmod -R a+rX "$ihd_tmp/extract"
  if LD_LIBRARY_PATH="$ihd_libs" ldd "$ihd_dir/iHD_drv_video.so" | grep -q 'not found'; then
    echo "Incomplete iHD package dependencies; refusing live test"; return 3
  fi
  local log="$ihd_tmp/vainfo.log"
  if ! timeout -k 2s 15s runuser -u veyra -- env \
    LIBVA_DRIVER_NAME=iHD LIBVA_DRIVERS_PATH="$ihd_dir" LD_LIBRARY_PATH="$ihd_libs" \
    vainfo --display drm --device /dev/dri/renderD128 >"$log" 2>&1; then
    echo "iHD failed initialization"; tail -18 "$log"; return 3
  fi
  grep -Eq 'VAProfileH264(High|Main)[[:space:]]*:[[:space:]]*VAEntrypointEncSliceLP' "$log" || {
    echo "iHD does not advertise low-power H264 encoding"; return 3;
  }
  echo "PASS: scoped iHD driver initialized; testing 50 synthetic frames before touching recorder."
  if ! timeout -k 2s 15s runuser -u veyra -- env \
      LIBVA_DRIVER_NAME=iHD LIBVA_DRIVERS_PATH="$ihd_dir" LD_LIBRARY_PATH="$ihd_libs" \
      ffmpeg -hide_banner -loglevel error -nostdin \
      -vaapi_device /dev/dri/renderD128 \
      -f lavfi -i 'testsrc2=size=1280x720:rate=25' -frames:v 50 -an \
      -vf 'format=nv12,hwupload' -c:v h264_vaapi -low_power 1 -qp 23 \
      -f h264 -y /dev/null >"$ihd_tmp/synthetic.log" 2>&1; then
    echo "H264 encoder preflight failed; original recorder untouched."
    tail -18 "$ihd_tmp/synthetic.log"; return 3
  fi
  echo "PASS: iHD H264 encoder functional without system installation."
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
  stage_ihd
  route
  failsafe="veyra-v070-resume-$(date +%s)-$$"
  # Independent timer validates PID still belongs to recorder before resuming.
  systemd-run --quiet --collect --unit="$failsafe" --on-active=14520s \
    /usr/bin/bash -c 'p="$1"; c="$2"; if [[ -r "/proc/$p/cmdline" ]] && tr "\0" " " < "/proc/$p/cmdline" | grep -Fq "x11grab" && grep -Fq "$c" "/proc/$p/cgroup"; then kill -CONT "$p"; fi' \
    _ "$ffpid" "$cg"
  kill -STOP "$ffpid"
  paused=1
  echo "Paused ONLY the previous recorder FFmpeg; original Chrome and VNC remain running."
  local output
  output="[f=mpegts:onfail=abort]udp://127.0.0.1:$PORT?pkt_size=1316|[f=segment:segment_time=4:segment_wrap=10:segment_format=mpegts:reset_timestamps=1]$BASE/segments/segment%02d.ts"
  setsid runuser -u veyra -- env DISPLAY=:92 XDG_RUNTIME_DIR="$RUNTIME" PULSE_SERVER="$PULSE" \
    LIBVA_DRIVER_NAME=iHD LIBVA_DRIVERS_PATH="$ihd_dir" LD_LIBRARY_PATH="$ihd_libs" \
    /usr/bin/ffmpeg -hide_banner -loglevel info -stats_period 5 -stats -benchmark -nostdin \
    -vaapi_device /dev/dri/renderD128 \
    -thread_queue_size 256 -f x11grab -framerate 25 -video_size 1366x768 -i :92.0 \
    -thread_queue_size 512 -f pulse -sample_rate 48000 -channels 2 -i "$SINK.monitor" \
    -t "$DURATION" -map 0:v:0 -map 1:a:0 \
    -vf 'format=nv12,hwupload' \
    -c:v h264_vaapi -low_power 1 -qp 23 -g 25 -bf 0 \
    -c:a mp2 -b:a 160k -ar 48000 -ac 2 \
    -muxdelay 0 -muxpreload 0 -f tee "$output" \
    >"$BASE/encoder.log" 2>&1 &
  encpid=$!
  sleep 3
  kill -0 "$encpid" 2>/dev/null || { echo "Encoder quit early"; return 5; }
  echo "One Intel GPU H264 encoder now serves both the ring buffer and physical player."
  setsid runuser -u veyra -- env XDG_RUNTIME_DIR="$RUNTIME" \
    WAYLAND_DISPLAY="$sock" PULSE_SERVER="$PULSE" PULSE_SINK="$physical" \
    SDL_VIDEODRIVER=wayland SDL_AUDIODRIVER=pulseaudio \
    /usr/bin/ffplay -hide_banner -loglevel warning -nostats -fs -noborder \
    -framedrop -sync audio -probesize 65536 \
    -i "udp://127.0.0.1:$PORT?fifo_size=1000000&overrun_nonfatal=1" \
    >"$BASE/player.log" 2>&1 &
  playerpid=$!
  echo "TV session live; up to 4 hours, with fail-safe recorder restoration."
  echo "Use 'sudo systemctl stop veyra-tv-v070.service' to stop the trial safely."
  set +e
  wait "$encpid"
  local code=$?
  set -e
  if (( code )); then echo "Shared encoder stopped unexpectedly: exit $code"; return "$code"; fi
  echo "TV SESSION FINISHED:"
  grep -E 'frame=.*fps=.*speed=|bench: ' "$BASE/encoder.log" | tail -8 || true
  echo "Programme video and audio shared one capture stream; short ring segments were generated."
  echo "Temporary media will be deleted and the original recorder resumed by cleanup."
}
emergency_resume() {
  local cg2 pid2 cmd2
  cg2=$(systemctl show -p ControlGroup --value "$CAP" 2>/dev/null || true)
  [[ -n "$cg2" && -d "/sys/fs/cgroup$cg2" ]] || { echo "Recorder service cgroup unavailable"; return 1; }
  while read -r pid2; do
    [[ "$pid2" =~ ^[0-9]+$ && -r "/proc/$pid2/cmdline" ]] || continue
    [[ "$(cat "/proc/$pid2/comm" 2>/dev/null)" == ffmpeg ]] || continue
    cmd2=$(tr '\0' ' ' < "/proc/$pid2/cmdline")
    if [[ "$cmd2" == *x11grab* && "$cmd2" == *:92* ]]; then
      kill -CONT "$pid2" && echo "PASS: original capture FFmpeg resumed ($pid2)" && return 0
    fi
  done < <(find "/sys/fs/cgroup$cg2" -name cgroup.procs -exec cat {} + | sort -un)
  echo "No original recorder PID found to resume"
  return 2
}
case "${1:-}" in
  preflight) preflight ;;
  start) run ;;
  recover) emergency_resume ;;
  status)
    for u in "$CAP" "$VNC" veyra-kiosk.service veyra-tv-v070.service; do echo "$u: $(systemctl is-active "$u" 2>/dev/null || true)"; done
    echo "HDMI: $(cat /sys/class/drm/card0-HDMI-A-1/status 2>/dev/null || echo not-found)"
    [[ -f "$BASE/encoder.log" ]] && tail -3 "$BASE/encoder.log" || true
    ;;
  *) echo "Usage: sudo bash $0 {preflight|start|status|recover}"; exit 2 ;;
esac
