#!/usr/bin/env bash
# Veyra non-disruptive motion probe v0.5.4
# Does not stop/restart services or retain video/audio.
set -Eeuo pipefail
(( EUID == 0 )) || { echo "Use sudo"; exit 2; }
[[ -S /tmp/.X11-unix/X92 ]] || { echo "Virtual :92 display unavailable"; exit 2; }
command -v ffmpeg >/dev/null
if systemctl is-active --quiet veyra-live-av-v052.service || systemctl is-active --quiet veyra-live-av-v051.service; then
  echo "Wait until physical live playback test ends before sampling"; exit 3
fi
echo "=== CURRENT SERVICES ==="
for u in veyra-kiosk.service veyra-virtual-loopback-v01.service veyra-itvx-vnc-v01.service; do
  echo "$u: $(systemctl is-active "$u" 2>/dev/null || true)"
done
echo "=== PROCESS CPU ==="
ps -eo comm,pcpu --sort=-pcpu | grep -E '(^COMM|^chrome |^Xvfb |^ffmpeg |^ffplay )' | head -15 || true
echo "=== WAYLAND OUTPUT MODE (IF AVAILABLE) ==="
if command -v wlr-randr >/dev/null 2>&1; then
  vuid=$(id -u veyra)
  sock=$(find "/run/user/$vuid" -maxdepth 1 -name 'wayland-*' -type s -printf '%f\n' 2>/dev/null | head -1 || true)
  if [[ -n "$sock" ]]; then
    runuser -u veyra -- env XDG_RUNTIME_DIR="/run/user/$vuid" WAYLAND_DISPLAY="$sock" wlr-randr 2>&1 | head -25 || true
  fi
else
  echo "Refresh mode not yet confirmed (wlr-randr unavailable)."
fi
echo "=== VIRTUAL DISPLAY MOTION (NO MEDIA STORED) ==="
echo "Sampling 640x360 centre at 50 Hz for 16 seconds."
python3 - <<'PY'
import collections, re, statistics, subprocess, time
cmd=['runuser','-u','veyra','--','env','DISPLAY=:92',
     '/usr/bin/ffmpeg','-hide_banner','-nostdin','-loglevel','error',
     '-f','x11grab','-framerate','50','-video_size','640x360',
     '-i',':92.0+363,204','-t','16',
     '-vf','scale=160:90:flags=fast_bilinear,format=gray,'
           'tblend=all_mode=difference,signalstats,'
           'metadata=print:key=lavfi.signalstats.YAVG:file=-',
     '-an','-f','null','-']
start=time.monotonic()
try:
    r=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                     text=True,timeout=26)
except subprocess.TimeoutExpired:
    raise SystemExit('Capture timed out; all services remain untouched')
if r.returncode:
    raise SystemExit('Capture failed: '+r.stderr[-600:])
p=re.compile(r'frame:\s*\d+\s+pts:\s*-?\d+\s+pts_time:([\d.]+)\s*\n'
             r'lavfi\.signalstats\.YAVG=([\d.]+)')
samples=[(float(t),float(y)) for t,y in p.findall(r.stdout)]
if len(samples)<30:
    raise SystemExit('Too few samples (%s)' % len(samples))
print('Wall time %.2fs; received %s frame-pair samples.' %
      (time.monotonic()-start,len(samples)))
for threshold,name in ((0.15,'small image changes'),(0.6,'significant motion')):
    changes=[t for t,y in samples if y>=threshold]
    intervals=[round((b-a)*1000) for a,b in zip(changes,changes[1:]) if b>a]
    binned=collections.Counter(int(t) for t in changes)
    print('\n%s (threshold %.2f)' % (name,threshold))
    print('  changed frames:',len(changes),'/',len(samples))
    print('  common intervals (ms):',
          collections.Counter(n for n in intervals if 10<=n<=150).most_common(8))
    print('  changes each second:',[binned[n] for n in range(16)])
    if intervals:
        print('  median %sms, longest %sms' %
              (statistics.median(intervals),max(intervals)))
    if sum(binned[n]>=12 for n in range(16))<4:
        print('  CAUTION: insufficient moving content to infer steady cadence.')
print('\nInterpretation: 40ms changes ~= 25fps; 20ms ~= 50fps.')
print('Mixtures can represent 24/25/30fps in a 50Hz sample, plus jitter.')
print('This is rendered-pixel timing, not original encoded stream metadata.')
PY
echo "=== PREVIOUS PLAYER PERFORMANCE ==="
journalctl -u veyra-live-av-v052.service -n 180 --no-pager 2>/dev/null |
  grep -E 'frame=|fps=|speed=|drop=|Error|error' | tail -10 || true
echo "DONE: no browser, VNC or kiosk restart, and no media retained."
