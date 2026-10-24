#!/usr/bin/env bash
# VEYRA playback isolation v1.3: replay the SAME v1.2 OBS MKV using VAAPI vs software.
# Read-only: no OBS startup, no recording, no changes to :92, Chrome, Cage, or services.
set -Eeuo pipefail

ROOT=/opt/veyra/obs-backend-v1/av-qa-v12/runs
USER_NAME=veyra
block() { echo "SAFETY STOP: $*" >&2; return 2; }

clip_path() {
  local selected="${1:-}"
  if [[ -z "$selected" ]]; then
    selected=$(find "$ROOT" -type f -path '*/buffer/*.mkv' -print0 2>/dev/null |
      sort -z | tail -z -n 1 | tr -d '\0')
  fi
  [[ -n "$selected" ]] || { block "no v1.2 MKV found"; return 2; }
  selected=$(realpath -e -- "$selected") || return 2
  case "$selected" in
    "$ROOT"/*/buffer/*.mkv) ;;
    *) block "only known OBS v1.2 MKV files are permitted"; return 2 ;;
  esac
  [[ -s "$selected" ]] || { block "recording is empty"; return 2; }
  echo "$selected"
}
preflight() {
  [[ $EUID -eq 0 ]] || { block "run under sudo"; return 2; }
  for cmd in mpv ffprobe runuser pactl; do
    command -v "$cmd" >/dev/null || { block "missing $cmd"; return 2; }
  done
  for svc in veyra-kiosk.service veyra-virtual-loopback-v01.service veyra-itvx-vnc-v01.service; do
    systemctl is-active --quiet "$svc" || { block "protected $svc inactive"; return 2; }
  done
  echo "PASS: original recorder, kiosk and VNC active."
}
inspect() {
  preflight
  local f="$1" job
  job=$(dirname "$(dirname "$f")")
  echo "=== SAVED OBS MKV, no new recording ==="
  echo "FILE=$f"
  ffprobe -v warning -show_entries 'format=duration,size:stream=codec_name,codec_type,width,height,avg_frame_rate'     -of default=noprint_wrappers=1 "$f"
  echo "=== OBS CAPTURE / ENCODER OBSERVATIONS ==="
  if [[ -r "$job/logs/obs-console.log" ]]; then
    grep -Ei 'OpenGL on adapter|llvmpipe|renderer|lagged frames|skipped frames|encoding overloaded|stalled|dropped frames|recording stopped|Output.*stopped|x264'       "$job/logs/obs-console.log" | tail -30 || true
  else
    echo "OBS log unavailable at $job/logs/obs-console.log"
  fi
  echo "=== HARDWARE DECODER ==="
  if [[ -e /dev/dri/renderD128 ]]; then
    ls -l /dev/dri/renderD128
  else
    echo "WARN: Intel render device absent"
  fi
  echo "OBS log counters do not by themselves prove MKV frame loss or smoothness."
}
play() {
  local mode="$1" f="$2" rt sock sink job log flag result=0
  preflight
  rt="/run/user/$(id -u "$USER_NAME")"
  sock=$(find "$rt" -maxdepth 1 -type s -name 'wayland-*' -printf '%f\n' | sort | head -1)
  [[ -n "$sock" ]] || { block "existing Cage Wayland socket missing"; return 2; }
  sink=$(runuser -u "$USER_NAME" -- env XDG_RUNTIME_DIR="$rt"     PULSE_SERVER="unix:$rt/pulse/native" pactl list short sinks |
    awk '$2~/^alsa_output/{print $2;exit}')
  [[ -n "$sink" ]] || { block "physical audio sink missing"; return 2; }
  job=$(dirname "$(dirname "$f")")
  log="$job/logs/mpv-replay-$mode.log"
  [[ -d "$job/logs" ]] || { block "trial logs directory unavailable"; return 2; }
  [[ "$mode" == hw ]] && flag=vaapi || flag=no
  echo "REPLAY_DECODER=$flag FILE=$f"
  echo "Original OBS MKV will be replayed on physical screen; no new capture."
  runuser -u "$USER_NAME" -- env     XDG_RUNTIME_DIR="$rt" WAYLAND_DISPLAY="$sock"     PULSE_SERVER="unix:$rt/pulse/native" PULSE_SINK="$sink" LIBVA_DRIVER_NAME=i965     timeout -k 2s 45s mpv --no-config --fullscreen --no-border       --vo=gpu --gpu-context=wayland --hwdec="$flag" --ao=pulse       --msg-level=vd=info --log-file="$log" "$f" || result=$?
  echo "MPV_EXIT=$result"
  echo "=== MPV DECODE / VIDEO OUTPUT REPORT ==="
  if [[ -r "$log" ]]; then
    grep -Ei 'using hardware decoding|hardware decoding|VO:|AO:|dropped|mistimed|video.*fps|failed|error' "$log" | tail -35 || true
  else
    echo "Playback log missing: $log"
  fi
  if [[ "$mode" == hw ]] && [[ -r "$log" ]] &&
       ! grep -Eiq 'Using hardware decoding \(vaapi\)' "$log"; then
    echo "WARNING: VAAPI was requested but hardware decoding was NOT confirmed in the mpv log."
    echo "Do not infer that hardware decode accelerated this replay."
  fi
  if [[ "$result" -ne 0 ]]; then
    echo "WARN: nonzero mpv exit; review printed log. Existing services unchanged."
    return "$result"
  fi
  echo "Playback finished; no OBS/Chrome/VNC/recorder service changes."
}
usage() {
  echo "Usage: sudo bash $0 {inspect|play-hw|play-sw} [full-v1.2-MKV-path]"
  exit 2
}
[[ $# -ge 1 && $# -le 2 ]] || usage
case "$1" in
  inspect|play-hw|play-sw) ;;
  *) usage ;;
esac
selected=$(clip_path "${2:-}") || exit 2
case "$1" in
  inspect) inspect "$selected" ;;
  play-hw) play hw "$selected" ;;
  play-sw) play sw "$selected" ;;
esac
