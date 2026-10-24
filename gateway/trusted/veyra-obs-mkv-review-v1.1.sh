#!/usr/bin/env bash
# VEYRA OBS MKV review: no capture, encode, stream, or service changes.
set -Eeuo pipefail
BASE=/opt/veyra/obs-backend-v1/av-qa-v11
OUT="$BASE/buffer"
RUNTIME=/run/user/999

find_file() {
  [[ $EUID -eq 0 ]] || { echo 'Use sudo'; return 2; }
  local files=()
  [[ -d "$OUT" ]] || { echo "No OBS QA buffer directory"; return 2; }
  mapfile -d '' -t files < <(find "$OUT" -maxdepth 1 -type f -name '*.mkv' -print0 | sort -z)
  if (( \${#files[@]} != 1 )); then
    echo "Expected exactly one OBS quality MKV; refuse ambiguous file selection."
    return 2
  fi
  QA_FILE="\${files[0]}"
  [[ -s "$QA_FILE" ]] || { echo "MKV empty"; return 2; }
}
inspect_file() {
  find_file
  printf '=== FILE %s ===\n' "$QA_FILE"
  ffprobe -hide_banner -v error \
    -show_entries 'format=duration,size,format_name:stream=index,codec_type,codec_name,width,height,avg_frame_rate,sample_rate,channels,bit_rate' \
    -of json "$QA_FILE"
  echo "=== VIDEO FRAMES ==="
  ffprobe -hide_banner -v error -select_streams v:0 -count_frames \
    -show_entries stream=nb_read_frames,avg_frame_rate -of compact "$QA_FILE" || true
  echo "=== OBS METRICS ==="
  grep -Ei 'missed frames|lagged frames|dropped frames|recording|streaming|failed|error|software|llvmpipe|VAAPI|xshm|pulse' \
    "$BASE/logs/obs-console.log" 2>/dev/null | tail -28 || true
  echo "Codec streams alone cannot prove ITVX picture is visible or sound is audible."
}
play_file() {
  find_file
  [[ -S "$RUNTIME/pulse/native" ]] || { echo "Pulse unavailable"; return 2; }
  local socket speaker
  socket=$(find "$RUNTIME" -maxdepth 1 -type s -name 'wayland-*' -printf '%f\n' | sort | head -1)
  [[ -n "$socket" ]] || { echo "Physical Cage Wayland unavailable"; return 2; }
  speaker=$(runuser -u veyra -- env XDG_RUNTIME_DIR="$RUNTIME" PULSE_SERVER="unix:$RUNTIME/pulse/native" pactl list short sinks | awk '$2 ~ /^alsa_output/ {print $2; exit}')
  [[ -n "$speaker" ]] || { echo "No physical speaker found"; return 2; }
  echo "Playing saved OBS MKV on physical Lenovo display. This does not run OBS or capture."
  runuser -u veyra -- env XDG_RUNTIME_DIR="$RUNTIME" WAYLAND_DISPLAY="$socket" \
    PULSE_SERVER="unix:$RUNTIME/pulse/native" PULSE_SINK="$speaker" \
    LIBVA_DRIVER_NAME=i965 \
    mpv --no-config --fullscreen --no-border --vo=gpu --gpu-context=wayland \
    --hwdec=vaapi --ao=pulse "$QA_FILE"
}
case "\${1:-}" in
  inspect) inspect_file ;;
  play) play_file ;;
  *) echo "Usage: sudo bash $0 {inspect|play}"; exit 2 ;;
esac
