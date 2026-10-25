#!/usr/bin/env bash
# VEYRA OBS performance forensic report v1 — READ ONLY, for a saved v1.2 capture.
# No process control, no services changed, no video pixels or Chrome details collected.
set -Eeuo pipefail
ROOT=/opt/veyra/obs-backend-v1/av-qa-v12/runs
[[ "$EUID" == 0 ]] || { echo "Please execute through sudo." >&2; exit 2; }
for svc in veyra-kiosk.service veyra-itvx-vnc-v01.service veyra-virtual-loopback-v01.service; do
  printf 'PRESERVED_SERVICE %s=' "$svc"
  systemctl is-active "$svc" || true
done
echo "=== HARDWARE & MEMORY ==="
grep -m1 'model name' /proc/cpuinfo || true
free -h || true
for x in /dev/dri/renderD128 /tmp/.X11-unix/X92; do
  if [[ -e "$x" ]]; then echo "PRESENT $x"; else echo "ABSENT $x"; fi
done
echo "=== CURRENT PROCESS CPU; COMMAND LINES NOT SHOWN ==="
ps -eo pid,comm,pcpu,pmem,stat --sort=-pcpu | awk 'NR==1 || $2 ~ /^(obs|ffmpeg|Xvfb|mpv|chrome|chrome-bin|chromium|Xorg)$/' | head -25 || true
echo "=== RECORDINGS ==="
if [[ ! -d "$ROOT" ]]; then
  echo "NO v1.2 recording directory available"
  exit 3
fi
last=$(find "$ROOT" -mindepth 1 -maxdepth 1 -type d -printf '%p\n' | sort | tail -1)
[[ -n "$last" ]] || { echo "No OBS v1.2 trials found"; exit 3; }
echo "LATEST_TRIAL=$last"
echo "=== OBS SOURCE/RENDER/ENCODER QUALITY COUNTERS ==="
log="$last/logs/obs-console.log"
if [[ -r "$log" ]]; then
  grep -Ei 'OpenGL on adapter|llvmpipe|software rasterizer|rendering lag|stalls|encoding lag|skipped frames|dropped frames|Output.*stopped|total frames output|frames drawn|average time to render|lagged frames|output.*record|video stopped|encoder|preset|x264|failed|error' "$log" |
    tail -85 | cut -c 1-180 || true
  echo "--- OBS END OF LOG ---"
  tail -24 "$log" | cut -c 1-180
else
  echo "OBS trial log unavailable"
fi
echo "=== SAVED CAPTURE FRAME METADATA ==="
clip=$(find "$last/buffer" -maxdepth 1 -type f -name '*.mkv' -print -quit 2>/dev/null || true)
if [[ -n "$clip" ]]; then
  echo "FILE=$(basename "$clip")"
  ffprobe -v error -show_entries format=duration,size:stream=index,codec_type,codec_name,avg_frame_rate,nb_frames     -of default=noprint_wrappers=1 "$clip" || true
  ffprobe -v error -count_frames -select_streams v:0 -show_entries stream=nb_read_frames     -of default=noprint_wrappers=1 "$clip" || true
else
  echo "No MKV available in latest trial"
fi
echo "=== HARDWARE REPLAY LOG (IF PREVIOUSLY RUN) ==="
for plog in "$last/logs/mpv-replay-hw.log" "$last/logs/mpv-replay-sw.log"; do
  if [[ -r "$plog" ]]; then
    echo "LOG=$(basename "$plog")"
    grep -Ei 'Using hardware decoding|VO:|AO:|dropped|mistimed|Decoder|failed|error|fps' "$plog" | tail -25 | cut -c 1-180 || true
  fi
done
echo "=== REPORT COMPLETE: no system or recording changes ==="
