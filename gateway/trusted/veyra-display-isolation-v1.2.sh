#!/usr/bin/env bash
# VEYRA v1.2 DISPLAY-ONLY TEST — no OBS, no stream, no recorder changes.
# Tests whether a separate mpv window can become visible over existing Cage.
set -Eeuo pipefail
BASE=/opt/veyra/obs-backend-v1/display-test-v12
RUNTIME=/run/user/999
[[ "$EUID" -eq 0 ]] || { echo "Run with sudo"; exit 2; }
for svc in veyra-kiosk.service veyra-virtual-loopback-v01.service veyra-itvx-vnc-v01.service; do
  systemctl is-active --quiet "$svc" || { echo "SAFETY STOP: $svc not active"; exit 2; }
done
test -x /usr/bin/mpv || { echo "SAFETY STOP: mpv unavailable"; exit 2; }
test -S /tmp/.X11-unix/X92 || { echo "SAFETY STOP: existing ITVX :92 unavailable"; exit 2; }
socket=$(find "$RUNTIME" -maxdepth 1 -type s -name 'wayland-*' -printf '%f\n' | sort | head -1)
test -n "$socket" || { echo "SAFETY STOP: physical Wayland socket missing"; exit 2; }
install -d -o veyra -g veyra -m 700 "$BASE"
python3 - "$BASE/pattern.ppm" <<'PY'
from pathlib import Path
import sys
w,h=480,270
bars=((255,38,30),(28,210,64),(18,85,255),(255,235,42))
with Path(sys.argv[1]).open("wb") as f:
    f.write(f"P6\n{w} {h}\n255\n".encode())
    for y in range(h):
        row=bytearray()
        for x in range(w):
            rgb=bars[min(3,x//120)]
            if y>=220:
                rgb=((255,255,255) if (x//10)%2 else (0,0,0))
            elif 105<=y<120:
                rgb=(0,0,0)
            row.extend(rgb)
        f.write(row)
PY
chown veyra:veyra "$BASE/pattern.ppm"
chmod 600 "$BASE/pattern.ppm"
echo "VEYRA STATIC DISPLAY TEST: bright red/green/blue/yellow bars plus black-white stripes should fill the laptop screen for approximately 12 seconds."
echo "Chrome, VNC, Cage, OBS, original recorder, and the physical display configuration are unchanged."
set +e
runuser -u veyra -- env XDG_RUNTIME_DIR="$RUNTIME" WAYLAND_DISPLAY="$socket" \
  timeout --signal=TERM -k 2s 12s /usr/bin/mpv \
  --no-config --no-audio --fullscreen --no-border \
  --vo=gpu --gpu-context=wayland --hwdec=no \
  --image-display-duration=inf --loop-file=inf \
  "$BASE/pattern.ppm" > "$BASE/mpv.log" 2>&1
rc=$?
set -e
echo "MPV_EXIT=$rc (124 means intentional 12-second end)"
echo "=== MPV DISPLAY DIAGNOSTICS ==="
tail -20 "$BASE/mpv.log"
echo "=== OBS LAST LIVE SOURCE STARTUP (read only) ==="
obslog=/opt/veyra/obs-backend-v1/av-qa-v11/logs/obs-console.log
grep -Ei 'xshm|source|scene|pulse|OpenGL|renderer|failed|error|audio' "$obslog" 2>/dev/null | head -35 || true
echo "=== PROTECTED SERVICE STATUS ==="
for svc in veyra-kiosk.service veyra-virtual-loopback-v01.service veyra-itvx-vnc-v01.service; do
  printf '%s=' "$svc"
  systemctl is-active "$svc" || true
done
if [[ "$rc" != 0 && "$rc" != 124 ]]; then
  echo "DIAGNOSE: mpv did not finish normally; use its error above before any new capture."
  exit 4
fi
echo "DIAGNOSE: Did the laptop visibly show the FOUR COLOURED BARS? mpv startup alone does not prove visible output."
