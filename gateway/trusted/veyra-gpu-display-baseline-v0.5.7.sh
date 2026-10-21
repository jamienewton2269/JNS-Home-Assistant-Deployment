#!/usr/bin/env bash
# VEYRA v0.5.7 GPU-native video path baseline
# READ ONLY. Do not restart Chrome, VNC, Cage, or video services.
set -Eeuo pipefail
echo "=== VEYRA GPU / DISPLAY BASELINE v0.5.7 ==="
echo "Time: $(date -Is)"
echo "Host: $(hostname)"
echo
echo "=== VIDEO HARDWARE ==="
if command -v lspci >/dev/null 2>&1; then
  lspci -nnk | grep -EA4 'VGA compatible controller|Display controller|3D controller' || true
else
  echo "lspci not installed"
fi
echo
echo "=== GPU DEVICES AND PERMISSIONS ==="
ls -l /dev/dri/ 2>&1 || true
id veyra || true
echo
echo "=== DRM CONNECTORS ==="
found=0
for connector in /sys/class/drm/card*-eDP-* /sys/class/drm/card*-HDMI-* /sys/class/drm/card*-DP-* /sys/class/drm/card*-LVDS-*; do
  [[ -d "$connector" ]] || continue
  found=1
  printf '%s: ' "$(basename "$connector")"
  cat "$connector/status" 2>/dev/null || echo unknown
  if [[ -f "$connector/modes" ]]; then
    echo "Supported resolutions:"
    sort -u "$connector/modes" | head -15
  fi
done
if (( found == 0 )); then echo "No matching DRM connectors discovered"; fi
echo
echo "=== EDID TIMING MODES ==="
python3 - <<'PY'
from pathlib import Path
paths=list(Path('/sys/class/drm').glob('card*-*/edid'))
seen=0
for p in paths:
    try:
        d=p.read_bytes()
    except OSError:
        continue
    if len(d)<128 or d[:8]!=b'\x00\xff\xff\xff\xff\xff\xff\x00':
        continue
    seen+=1
    print(str(p.parent.name)+':')
    for offset in (54,72,90,108):
        b=d[offset:offset+18]
        if len(b)<18:continue
        pixelclock=int.from_bytes(b[0:2],'little')*10000
        if not pixelclock:continue
        ha=b[2]+((b[4]>>4)<<8)
        hb=b[3]+((b[4]&15)<<8)
        va=b[5]+((b[7]>>4)<<8)
        vb=b[6]+((b[7]&15)<<8)
        if ha and va and ha+hb and va+vb:
            hz=pixelclock/((ha+hb)*(va+vb))
            print('  %s x %s : %.2f Hz (EDID detailed timing)'%(ha,va,hz))
if not seen:print('No readable panel EDID available.')
print('EDID lists supported timings; it does NOT establish the currently selected refresh rate.')
PY
echo
echo "=== CURRENT DRM MODE (if kernel debug data is already available) ==="
for state in /sys/kernel/debug/dri/*/state; do
  [[ -r "$state" ]] || continue
  echo "$state"
  grep -E '^\s*crtc\[|^\s*mode:|^\s*active=|^\s*enable=' "$state" 2>/dev/null | head -40 || true
done
echo
echo "=== VA-API DRIVER ==="
if command -v vainfo >/dev/null 2>&1; then
  render=''
  for d in /dev/dri/renderD*; do [[ -c "$d" ]] && { render="$d"; break; }; done
  if [[ -n "$render" ]]; then
    echo "Testing VA-API on $render as user veyra (up to 8 seconds)"
    timeout 8 runuser -u veyra -- vainfo --display drm --device "$render" 2>&1 | grep -E 'VA-API|Driver version|H264|HEVC|VP9|VAEntrypoint|failed|error' | head -55 || true
  else
    echo 'No render node available'
  fi
else
  echo 'vainfo not installed; no software installed or modified'
fi
echo
echo "=== FFMPEG HARDWARE SUPPORT ==="
ffmpeg -hide_banner -hwaccels 2>/dev/null | head -25 || true
ffmpeg -hide_banner -encoders 2>/dev/null | grep -E 'h264_vaapi|hevc_vaapi|mjpeg_vaapi' || true
echo
echo "=== WAYLAND SCREEN-CAPTURE CAPABILITIES ==="
if command -v wayland-info >/dev/null 2>&1; then
  uid=$(id -u veyra)
  sock=$(find "/run/user/$uid" -maxdepth 1 -type s -name 'wayland-*' -printf '%f\n' 2>/dev/null | sort | head -1 || true)
  if [[ -n "$sock" ]]; then
    timeout 5 runuser -u veyra -- env XDG_RUNTIME_DIR="/run/user/$uid" WAYLAND_DISPLAY="$sock" wayland-info 2>&1 |
      grep -E 'zwlr_screencopy_manager_v1|zwp_linux_dmabuf_v1|ext_image_copy_capture_manager_v1' | head -15 || true
  fi
else
  echo "wayland-info not installed"
fi
if command -v wl-screenrec >/dev/null 2>&1; then echo 'wl-screenrec is installed'; else echo 'wl-screenrec not installed'; fi
echo
echo "=== ACTIVE SERVICES (NO CHANGES) ==="
for svc in veyra-kiosk.service veyra-virtual-loopback-v01.service veyra-itvx-vnc-v01.service; do
  echo "$svc: $(systemctl is-active "$svc" 2>/dev/null || true)"
done
echo
echo "COMPLETE: read-only checks; no recording, profile changes, or restarts."
