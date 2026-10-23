#!/usr/bin/env bash
# Veyra v0.7.2: isolated 50fps target, 30-minute buffer and safe original-recorder recovery.
# Staged candidate; original v0.7.0, Cage, Chrome and VNC are not replaced.
# No global graphics driver changes. Synthetic encoder check BEFORE recorder pause.
# Does not restart virtual Chrome, VNC, Cage or change browser settings.
# Normal recorder FFmpeg only is SIGSTOPped for this test; independent timer restores it.
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || { echo "Use sudo"; exit 2; }
CAP=veyra-virtual-loopback-v01.service
VNC=veyra-itvx-vnc-v01.service
SINK=veyra_virtual_capture
PORT=23572
ROOT=/opt/veyra/virtual-loopback-v01
BASE="$ROOT/shared-test-v072"
FPS=50
SEGMENT_TIME=4
SEGMENT_COUNT=450
START_FREE_KB=4194304    # Minimum 4GiB initially free; runtime guard preserves at least 1GiB
STOP_FREE_KB=1048576
TV=veyra-tv-v072.service
OLDER=veyra-tv-v070.service
INSTALL_ROOT=/opt/veyra/tv-night-v072
UNITFILE=/etc/systemd/system/veyra-tv-v072.service
REC_MARKER=/run/veyra-tv-v072/recorder.pid
VUID=$(id -u veyra)
RUNTIME="/run/user/$VUID"
PULSE="unix:$RUNTIME/pulse/native"
DURATION=14400
paused=0
spacewatchpid=''
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
  if [[ "$spacewatchpid" =~ ^[0-9]+$ ]]; then kill "$spacewatchpid" 2>/dev/null || true; wait "$spacewatchpid" 2>/dev/null || true; fi
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
  if [[ "$ffpid" =~ ^[0-9]+$ ]] && kill -CONT "$ffpid" 2>/dev/null; then
    rm -f -- "$REC_MARKER"
    if (( paused )); then echo "RESTORED: original recording process resumed"; fi
  elif (( paused )); then
    echo "WARNING: direct resume was not confirmed; ownership marker retained for unit recovery." >&2
  fi
  if [[ -n "$failsafe" ]]; then systemctl stop "$failsafe.timer" 2>/dev/null || true; fi
  if [[ -n "$ihd_tmp" && -d "$ihd_tmp" ]]; then rm -rf -- "$ihd_tmp"; fi
  # Only remove segments in this isolated temporary trial folder.
  if [[ -d "$BASE/segments" ]]; then
    find "$BASE/segments" -maxdepth 1 -type f -name 'segment???.ts' -delete
  fi
  if (( rc != 0 )); then
    echo "Trial stopped with status $rc"
    [[ -f "$BASE/encoder.log" ]] && tail -35 "$BASE/encoder.log"
    [[ -f "$BASE/player.log" ]] && tail -20 "$BASE/player.log"
  fi
  exit "$rc"
}
preflight() {
  if systemctl is-active --quiet "$OLDER"; then
    echo "SAFETY STOP: v0.7.0 pilot is active."; return 2
  fi
  if [[ -s "$REC_MARKER" ]]; then
    echo "SAFETY STOP: previous v0.7.2 recorder marker still present; inspect service and recover before another start."; return 2
  fi
  if [[ -z "${INVOCATION_ID:-}" ]] && systemctl is-active --quiet "$TV"; then
    echo "SAFETY STOP: v0.7.2 pilot is already active."; return 2
  fi
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
  local free_kb
  free_kb=$(df -Pk "$ROOT" | awk 'NR==2{print $4}')
  if [[ ! "$free_kb" =~ ^[0-9]+$ ]] || (( free_kb < START_FREE_KB )); then
    echo "SAFETY STOP: need at least 4GiB free before 30-minute ring test; available ${free_kb:-unknown} KiB."
    return 2
  fi
  echo "PASS: recorder PID $ffpid; proposed FPS $FPS; ring ${SEGMENT_COUNT}x${SEGMENT_TIME}s=1800s; disk ${free_kb}KiB free."
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
  echo "PASS: scoped iHD driver initialized; testing 100 synthetic frames at 50fps before touching recorder."
  if ! timeout -k 2s 15s runuser -u veyra -- env \
      LIBVA_DRIVER_NAME=iHD LIBVA_DRIVERS_PATH="$ihd_dir" LD_LIBRARY_PATH="$ihd_libs" \
      ffmpeg -hide_banner -loglevel error -nostdin \
      -vaapi_device /dev/dri/renderD128 \
      -f lavfi -i 'testsrc2=size=1280x720:rate=50' -frames:v 100 -an \
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
  # systemctl stop sends TERM: cleanup restores the original recorder.
  # Treat an intentional stop as successful rather than a unit failure.
  trap 'exit 0' TERM
  mkdir -p "$BASE/segments"
  chown veyra:veyra "$BASE" "$BASE/segments"
  find "$BASE/segments" -maxdepth 1 -type f -name 'segment???.ts' -delete
  : >"$BASE/encoder.log"; : >"$BASE/player.log"
  chown veyra:veyra "$BASE/encoder.log" "$BASE/player.log"
  stage_ihd
  route
  failsafe="veyra-v072-resume-$(date +%s)-$"
  # Independent timer validates PID still belongs to recorder before resuming.
  systemd-run --quiet --collect --unit="$failsafe" --on-active=14520s \
    /usr/bin/bash -c 'p="$1"; c="$2"; if [[ -r "/proc/$p/cmdline" ]] && tr "\0" " " < "/proc/$p/cmdline" | grep -Fq "x11grab" && grep -Fq "$c" "/proc/$p/cgroup"; then kill -CONT "$p"; fi' \
    _ "$ffpid" "$cg"
  install -d -m 700 /run/veyra-tv-v072
  printf '%s\n' "$ffpid" > "$REC_MARKER"
  chmod 600 "$REC_MARKER"
  kill -STOP "$ffpid"
  paused=1
  echo "Paused ONLY the previous recorder FFmpeg; original Chrome and VNC remain running."
  local output
  output="[f=mpegts:onfail=abort]udp://127.0.0.1:$PORT?pkt_size=1316|[f=segment:onfail=abort:segment_time=$SEGMENT_TIME:segment_wrap=$SEGMENT_COUNT:segment_format=mpegts:reset_timestamps=1]$BASE/segments/segment%03d.ts"
  setsid runuser -u veyra -- env DISPLAY=:92 XDG_RUNTIME_DIR="$RUNTIME" PULSE_SERVER="$PULSE" \
    LIBVA_DRIVER_NAME=iHD LIBVA_DRIVERS_PATH="$ihd_dir" LD_LIBRARY_PATH="$ihd_libs" \
    /usr/bin/ffmpeg -hide_banner -loglevel info -stats_period 5 -stats -benchmark -nostdin \
    -vaapi_device /dev/dri/renderD128 \
    -thread_queue_size 256 -f x11grab -framerate "$FPS" -video_size 1366x768 -i :92.0 \
    -thread_queue_size 512 -f pulse -sample_rate 48000 -channels 2 -i "$SINK.monitor" \
    -t "$DURATION" -map 0:v:0 -map 1:a:0 \
    -vf 'format=nv12,hwupload' \
    -c:v h264_vaapi -low_power 1 -qp 23 -g "$FPS" -bf 0 \
    -c:a mp2 -b:a 160k -ar 48000 -ac 2 \
    -muxdelay 0 -muxpreload 0 -f tee "$output" \
    >"$BASE/encoder.log" 2>&1 &
  encpid=$!
  sleep 3
  kill -0 "$encpid" 2>/dev/null || { echo "Encoder quit early"; return 5; }
  echo "One hardware-H264 pipeline feeds TV and a 30-minute test ring."
  (
    while kill -0 "$encpid" 2>/dev/null; do
      sleep 15
      free_kb=$(df -Pk "$BASE" | awk 'NR==2{print $4}')
      if [[ ! "$free_kb" =~ ^[0-9]+$ ]] || (( free_kb < STOP_FREE_KB )); then
        echo "DISK GUARD: stopping v0.7.2 encoder before disk exhaustion." >&2
        kill -TERM -- "-$encpid" 2>/dev/null || true
        break
      fi
    done
  ) &
  spacewatchpid=$!
  setsid runuser -u veyra -- env XDG_RUNTIME_DIR="$RUNTIME" \
    WAYLAND_DISPLAY="$sock" PULSE_SERVER="$PULSE" PULSE_SINK="$physical" \
    SDL_VIDEODRIVER=wayland SDL_AUDIODRIVER=pulseaudio \
    /usr/bin/ffplay -hide_banner -loglevel warning -nostats -fs -noborder \
    -framedrop -sync audio -probesize 65536 \
    -i "udp://127.0.0.1:$PORT?fifo_size=1000000&overrun_nonfatal=1" \
    >"$BASE/player.log" 2>&1 &
  playerpid=$!
  echo "TV session live; up to 4 hours, with fail-safe recorder restoration."
  echo "Use 'sudo systemctl stop veyra-tv-v072.service' to stop the trial safely."
  set +e
  wait "$encpid"
  local code=$?
  set -e
  if (( code )); then echo "Shared encoder stopped unexpectedly: exit $code"; return "$code"; fi
  echo "TV SESSION FINISHED:"
  grep -E 'frame=.*fps=.*speed=|bench: ' "$BASE/encoder.log" | tail -8 || true
  echo "Shared stream used a 450-slot x 4-second rolling ring (30-minute target)."
  echo "Temporary media will be deleted and the original recorder resumed by cleanup."
}
emergency_resume() {
  local cg2 pid2 cmd2 owned
  [[ -s "$REC_MARKER" ]] || { echo "No v0.7.2 recorder ownership marker; nothing to recover"; return 0; }
  if systemctl is-active --quiet "$OLDER"; then echo "Original v0.7.0 pilot active: do not interfere"; return 2; fi
  read -r owned < "$REC_MARKER"
  [[ "$owned" =~ ^[0-9]+$ ]] || { echo "Invalid recorder marker"; return 2; }
  cg2=$(systemctl show -p ControlGroup --value "$CAP" 2>/dev/null || true)
  [[ -n "$cg2" && -d "/sys/fs/cgroup$cg2" ]] || { echo "Recorder service cgroup unavailable"; return 1; }
  while read -r pid2; do
    [[ "$pid2" =~ ^[0-9]+$ && -r "/proc/$pid2/cmdline" ]] || continue
    [[ "$(cat "/proc/$pid2/comm" 2>/dev/null)" == ffmpeg ]] || continue
    cmd2=$(tr '\0' ' ' < "/proc/$pid2/cmdline")
    if [[ "$pid2" == "$owned" && "$cmd2" == *x11grab* && "$cmd2" == *:92* ]]; then
      kill -CONT "$pid2" && rm -f -- "$REC_MARKER" && echo "PASS: owned original recorder resumed ($pid2)" && return 0
    fi
  done < <(find "/sys/fs/cgroup$cg2" -name cgroup.procs -exec cat {} + | sort -un)
  echo "No original recorder PID found to resume"
  return 2
}
install_candidate() {
  preflight
  if [[ -f "$UNITFILE" ]] && ! grep -Fq "/opt/veyra/tv-night-v072/current/player.sh" "$UNITFILE"; then
    echo "SAFETY STOP: existing unit owned by another application"; return 2
  fi
  install -d -m 755 "$INSTALL_ROOT"
  local stage stamp release
  stage=$(mktemp -d "$INSTALL_ROOT/.stage.XXXXXXXX")
  stamp=$(date +%Y%m%d-%H%M%S)
  release="$INSTALL_ROOT/v072-$stamp-${BASHPID}"
  install -m 755 "$0" "$stage/player.sh"
  bash -n "$stage/player.sh"
  mv "$stage" "$release"
  ln -s "$release" "$INSTALL_ROOT/.next.${BASHPID}"
  mv -Tf "$INSTALL_ROOT/.next.${BASHPID}" "$INSTALL_ROOT/current"
  cat > "$UNITFILE" <<'UNIT'
[Unit]
Description=VEYRA v0.7.2 isolated 50fps / 30-minute buffer quality trial
After=veyra-kiosk.service veyra-virtual-loopback-v01.service
Requires=veyra-virtual-loopback-v01.service

[Service]
Type=simple
ExecStart=/bin/bash /opt/veyra/tv-night-v072/current/player.sh run
ExecStopPost=-/bin/bash /opt/veyra/tv-night-v072/current/player.sh recover
WorkingDirectory=/opt/veyra/tv-night-v072/current
RuntimeDirectory=veyra-tv-v072
RuntimeDirectoryMode=0700
KillMode=mixed
TimeoutStartSec=180
TimeoutStopSec=30
RuntimeMaxSec=14500
Restart=no
NoNewPrivileges=yes

[Install]
WantedBy=multi-user.target
UNIT
  chmod 644 "$UNITFILE"
  systemctl daemon-reload
  echo "STAGED: v0.7.2 service created but DISABLED and NOT STARTED."
  echo "v0.7.0 playback, Chrome, VNC and Cage are untouched."
}
case "${1:-}" in
  preflight) preflight ;;
  install) install_candidate ;;
  start)
    [[ -f "$UNITFILE" ]] || { echo "Install staged unit first"; exit 2; }
    preflight
    systemctl start --no-block "$TV"
    echo "v0.7.2 start requested; inspect status and physical playback.";;
  stop) systemctl stop "$TV" ;;
  run) run ;;
  recover) emergency_resume ;;
  status)
    for u in "$CAP" "$VNC" veyra-kiosk.service "$OLDER" "$TV"; do echo "$u: $(systemctl is-active "$u" 2>/dev/null || true)"; done
    echo "HDMI: $(cat /sys/class/drm/card0-HDMI-A-1/status 2>/dev/null || echo not-found)"
    [[ -f "$BASE/encoder.log" ]] && tail -3 "$BASE/encoder.log" || true
    ;;
  *) echo "Usage: sudo bash $0 {preflight|install|start|status|stop|recover}"; exit 2 ;;
esac
