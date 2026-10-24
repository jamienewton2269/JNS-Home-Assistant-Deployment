#!/usr/bin/env bash
# VEYRA v1.2 — inspect the SAVED OBS MKV, no capture or streaming.
set -Eeuo pipefail
BASE=/opt/veyra/obs-backend-v1/av-qa-v11
FILE="$BASE/buffer/2026-10-24 18-37-25.mkv"
RUNTIME=/run/user/999
preflight() {
  [[ $EUID == 0 ]] || { echo 'Use sudo'; return 2; }
  [[ -s "$FILE" ]] || { echo "No saved third OBS recording: $FILE"; return 2; }
  [[ -x /usr/bin/mpv ]] || { echo 'mpv unavailable'; return 2; }
  for s in veyra-kiosk.service veyra-itvx-vnc-v01.service veyra-virtual-loopback-v01.service; do
    systemctl is-active --quiet "$s" || { echo "STOP: protected $s inactive"; return 2; }
  done
}
scan() {
  preflight
  local d t out
  d=$(mktemp -d /tmp/veyra-obs-frame-XXXXXXXX)
  chmod 700 "$d"
  trap 'rm -rf "$d"' EXIT
  for t in 4 14 24; do
    out="$d/$t"
    mkdir "$out"
    timeout -k 2s 12s mpv --no-config --no-audio --no-sub --hwdec=no \
      --start="$t" --frames=1 --vo=image --vo-image-format=png \
      --vo-image-outdir="$out" "$FILE" >"$d/$t.log" 2>&1 || {
        echo "FRAME_$t extraction warning:"; tail -5 "$d/$t.log";
      }
  done
  python3 - "$d" <<'PY'
from pathlib import Path
import sys,hashlib
base=Path(sys.argv[1]); vals=[]
try:
 from PIL import Image,ImageStat
 has_pillow=True
except ImportError: has_pillow=False
for t in (4,14,24):
 files=list((base/str(t)).glob('*.png'))
 if not files:
  print(f'SECOND={t}: NO_DECODED_FRAME'); continue
 f=files[0]; raw=f.read_bytes(); digest=hashlib.sha256(raw).hexdigest()[:12]
 msg=f'SECOND={t}: PNG_BYTES={len(raw)}, SHA256_PREFIX={digest}'
 if has_pillow:
  im=Image.open(f).convert('RGB')
  st=ImageStat.Stat(im.resize((96,54)))
  mean=sum(st.mean)/3; deviation=sum(st.stddev)/3
  msg+=f', RGB_MEAN={mean:.1f}/255, RGB_STDDEV={deviation:.1f}/255'
 print(msg); vals.append((len(raw),digest))
if not has_pillow:
 print('Pillow not installed: image size and fingerprint only, no pixel brightness metric.')
if len(vals)==3 and len(set(x[1] for x in vals))==1:
 print('All three decoded frames identical. Static or blank OBS recording; no programme motion demonstrated.')
print('Small nearly identical PNGs suggest a blank/static source, but are not definitive without visual inspection.')
PY
  echo '=== OBS SOURCE STARTUP ==='
  grep -iE 'XSHM|scene|pulse|capture|screen|OpenGL|renderer|source' "$BASE/logs/obs-console.log" 2>/dev/null | head -35 || true
  echo 'No new capture, stream or protected service change.'
}
play_sw() {
  preflight
  [[ -S "$RUNTIME/pulse/native" ]] || { echo 'Pulse unavailable'; return 2; }
  local sock speaker
  sock=$(find "$RUNTIME" -maxdepth 1 -type s -name 'wayland-*' -printf '%f\n' | sort | head -1)
  [[ -n "$sock" ]] || { echo 'Physical Wayland display unavailable'; return 2; }
  speaker=$(runuser -u veyra -- env XDG_RUNTIME_DIR="$RUNTIME" \
    PULSE_SERVER="unix:$RUNTIME/pulse/native" pactl list short sinks | awk '$2~/^alsa_output/ {print $2;exit}')
  [[ -n "$speaker" ]] || { echo 'Physical speaker unavailable'; return 2; }
  echo 'Playing the saved MKV with software H.264 decoding, not Intel VAAPI.'
  runuser -u veyra -- env XDG_RUNTIME_DIR="$RUNTIME" WAYLAND_DISPLAY="$sock" \
    PULSE_SERVER="unix:$RUNTIME/pulse/native" PULSE_SINK="$speaker" \
    /usr/bin/mpv --no-config --fullscreen --no-border --vo=gpu \
    --gpu-context=wayland --hwdec=no --ao=pulse "$FILE"
}
case "$1" in
 scan) scan;;
 play-sw) play_sw;;
 *) echo "Usage: sudo bash $0 scan | sudo bash $0 play-sw"; exit 2;;
esac
