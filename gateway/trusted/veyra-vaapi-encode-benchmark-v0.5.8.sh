#!/usr/bin/env bash
# Veyra v0.5.8: non-disruptive comparison of software and Intel VA-API encoders.
# Creates synthetic pixels only; encodes to /dev/null; never touches real ITVX content.
set -Eeuo pipefail

if (( EUID != 0 )); then echo 'Run with sudo'; exit 2; fi
DEV=/dev/dri/renderD128
[[ -c "$DEV" ]] || { echo "SAFETY STOP: GPU render device $DEV not available"; exit 2; }
command -v ffmpeg >/dev/null
id veyra >/dev/null

for unit in veyra-kiosk.service veyra-virtual-loopback-v01.service; do
  echo "$unit: $(systemctl is-active "$unit" 2>/dev/null || true)"
done

[[ -r /sys/class/drm/card0-eDP-1/status ]] && printf 'Laptop panel: %s\n' "$(cat /sys/class/drm/card0-eDP-1/status)"

DIR=$(mktemp -d /tmp/veyra-vaapi-v058.XXXXXXXX)
trap 'rm -rf -- "$DIR"' EXIT

run_trial() {
  local mode="$1" log="$DIR/$1.log" start end rc=0
  echo
  echo "=== $mode ==="
  start=$(date +%s%N)
  if [[ "$mode" == 'MPEG2_CPU' ]]; then
    timeout -k 3s 45s runuser -u veyra -- nice -n 10 \
      ffmpeg -hide_banner -benchmark -stats_period 2 -loglevel info -nostdin \
      -f lavfi -i 'testsrc2=size=1280x720:rate=25' \
      -frames:v 300 -an -threads 2 -c:v mpeg2video -q:v 7 -g 25 -bf 0 \
      -f mpeg2video -y /dev/null >"$log" 2>&1 || rc=$?
  else
    timeout -k 3s 45s runuser -u veyra -- nice -n 10 \
      ffmpeg -hide_banner -benchmark -stats_period 2 -loglevel info -nostdin \
      -vaapi_device "$DEV" \
      -f lavfi -i 'testsrc2=size=1280x720:rate=25' \
      -frames:v 300 -an -vf 'format=nv12,hwupload' \
      -c:v h264_vaapi -qp 23 -g 25 -bf 0 \
      -f h264 -y /dev/null >"$log" 2>&1 || rc=$?
  fi
  end=$(date +%s%N)
  python3 - "$mode" "$rc" "$start" "$end" "$log" <<'PY'
import re,sys
from pathlib import Path
mode,rc,start,end,log=sys.argv[1:]
s=Path(log).read_text(errors='replace')
print('Encoder:',mode)
print('Exit status:',rc)
print('Wall time: %.3fs'%((int(end)-int(start))/1e9))
bench=re.findall(r'bench:\s*(?:utime|rtime|stime|maxrss)[^\r\n]*',s)
for line in bench[-4:]:print(' ',line)
frames=re.findall(r'frame=\s*\d+[^\r\n]*',s)
for line in frames[-2:]:print(' ',line[:200])
if rc!='0':
    print('ERROR OUTPUT:')
    print('\n'.join(s.splitlines()[-18:]))
PY
  return "$rc"
}

run_trial MPEG2_CPU
if run_trial H264_VAAPI; then
  echo
  echo 'PASS: hardware H.264 encoder operational as user veyra.'
else
  echo 'H264 VA-API trial failed; previous services remain unchanged.'
  exit 3
fi

echo
printf '%s\n' 'Interpretation:' 'Both trials use the same 720p25 synthetic source.' \
  'The speed figures are encoder-throughput comparisons, NOT measurements of Chrome decode or 60Hz display pacing.' \
  'No video/audio files retained; no services, profiles, or display settings altered.'
