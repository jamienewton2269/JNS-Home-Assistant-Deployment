#!/usr/bin/env bash
# Veyra v0.5.3: read-only cadence/performance diagnostic.
# Samples frame changes; does not save pictures/audio or modify services.
set -Eeuo pipefail
if [[ $(id -u) != 0 ]]; then echo "Run with sudo"; exit 2; fi
LOG=/tmp/veyra-source-cadence-v053.log
USERID=$(id -u veyra)
echo "=== SERVICE STATUS ==="
for u in veyra-kiosk.service veyra-virtual-loopback-v01.service veyra-live-av-v052.service; do
  echo "$u: $(systemctl is-active "$u" 2>/dev/null || true)"
done
if systemctl is-active --quiet veyra-live-av-v052.service; then
  echo "The 25fps playback test is still running. Let it finish, then rerun this probe."
  exit 3
fi
echo "=== SOURCE DISPLAY (X11) ==="
ps -eo pid,pcpu,pmem,comm | awk '$4 ~ /Xvfb|ffmpeg|ffplay|chrome/ {print}' | head -20
echo "=== RECORDER SEGMENT PROPERTIES ==="
ls -t /opt/veyra/virtual-loopback-v01/buffer/segment*.ts 2>/dev/null | head -3 | while read -r f; do
  echo "$f"
  ffprobe -v error -select_streams v:0 -show_entries stream=codec_name,width,height,r_frame_rate,avg_frame_rate -of default=noprint_wrappers=1 "$f" || true
done
echo "Note: segment metadata describes Veyra's re-encoding, not ITVX's original stream."
echo "=== DISPLAY MOTION CADENCE ==="
echo "Sampling centre of virtual display at 50fps for 10 seconds; storing timestamps ONLY."
if ! runuser -u veyra -- env DISPLAY=:92 XDG_RUNTIME_DIR="/run/user/$USERID" \
  /usr/bin/ffmpeg -hide_banner -nostdin -loglevel info -stats_period 2 -stats \
  -f x11grab -framerate 50 -video_size 1366x768 -i :92.0 \
  -t 10 -vf 'crop=960:540:(iw-960)/2:(ih-540)/2,scale=320:180:flags=fast_bilinear,format=gray,mpdecimate=hi=768:lo=192:frac=0.05,showinfo' \
  -an -f null - >/dev/null 2>"$LOG"; then
  echo "Sampling failed. Diagnostic log: $LOG"
  tail -30 "$LOG"
  exit 4
fi
python3 - "$LOG" <<'PY'
import collections, re, sys, statistics
s=open(sys.argv[1],errors='replace').read()
times=[float(t) for t in re.findall(r'Parsed_showinfo[^\n]*?pts_time:\s*([0-9.]+)',s)]
deltas=[round((b-a)*1000) for a,b in zip(times,times[1:]) if b>a]
print('Detected unique image changes:',len(times))
print('Observed millisecond intervals (count):',collections.Counter(deltas).most_common(12))
if deltas:
    print('Median change interval:',statistics.median(deltas),'ms')
    print('Typical patterns: 20ms=50fps; 40ms=25fps; 33ms=30fps; 42ms=24fps.')
    print('These are displayed frame changes, not authoritative source-stream metadata.')
for line in s.splitlines():
    if 'speed=' in line and ('frame=' in line or 'fps=' in line):
        print('Capture performance:',line[-200:].strip())
PY
echo "=== PLAYER PERFORMANCE (RECENT) ==="
journalctl -u veyra-live-av-v052.service -n 100 --no-pager 2>/dev/null |
  grep -E 'frame=|speed=|fps=|drop|error|Error' | tail -16 || true
echo "DIAGNOSTIC COMPLETE. No media files saved. No services changed."
