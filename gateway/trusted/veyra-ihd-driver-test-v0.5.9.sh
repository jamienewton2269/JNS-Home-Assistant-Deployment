#!/usr/bin/env bash
# Veyra v0.5.9: isolated Intel iHD VA-API check / encode test.
# Never alters global graphics defaults or restarts media services.
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || { echo 'Run with sudo'; exit 2; }
ACTION=${1:-check}
[[ "$ACTION" == check || "$ACTION" == test ]] || { echo "Usage: sudo bash $0 {check|test}"; exit 2; }
DEVICE=/dev/dri/renderD128
[[ -c "$DEVICE" ]] || { echo "No Intel render device: $DEVICE"; exit 2; }
command -v ffmpeg >/dev/null
command -v vainfo >/dev/null
id veyra >/dev/null
echo '=== VEYRA INTEL iHD DRIVER v0.5.9 ==='
echo 'Installed package versions:'
dpkg-query -W -f='${Package} ${Version} ${Status}\n' \
  intel-media-va-driver intel-media-va-driver-non-free i965-va-driver i965-va-driver-shaders 2>/dev/null || true
echo
echo 'Driver libraries:'
find /usr/lib -name 'iHD_drv_video.so' -o -name 'i965_drv_video.so' 2>/dev/null | sort
echo
echo '=== iHD AS VEYRA USER (ENVIRONMENT SCOPED) ==='
if ! find /usr/lib -name 'iHD_drv_video.so' -print -quit 2>/dev/null | grep -q .; then
  echo 'iHD is not installed. Do not retry i965 hardware encode.'
  echo 'Debian package candidate: intel-media-va-driver (check apt-cache policy first).'
  exit 3
fi
log=$(mktemp /tmp/veyra-ihd-v059.XXXXXXXX)
trap 'rm -f "$log"' EXIT
set +e
timeout -k 3s 12s runuser -u veyra -- env LIBVA_DRIVER_NAME=iHD \
  vainfo --display drm --device "$DEVICE" > "$log" 2>&1
rc=$?
set -e
grep -E 'VA-API version|Driver version|H264|VAEntrypoint|failed|error' "$log" | head -65 || true
if (( rc != 0 )); then
  echo "iHD failed to initialise (exit $rc). No system configuration changed."
  tail -20 "$log"
  exit 4
fi
if [[ "$ACTION" == check ]]; then
  echo 'CHECK COMPLETE. No encoding attempted.'
  echo 'To test iHD encoder separately: sudo bash script test'
  exit 0
fi
if ! grep -Eq 'VAProfileH264(High|Main)[[:space:]]*:[[:space:]]*VAEntrypointEncSlice(LP)?' "$log"; then
  echo 'The iHD driver has not advertised a usable H.264 encoding entrypoint.'
  echo 'Encoder test skipped to avoid unnecessary crashes.'
  exit 5
fi
if grep -Eq 'VAProfileH264(High|Main)[[:space:]]*:[[:space:]]*VAEntrypointEncSlice$' "$log"; then
  extra=()
else
  extra=(-low_power 1)
fi
echo
echo "=== HARDWARE ENCODE: 720p25 SYNTHETIC FRAMES / iHD ==="
echo "Using ${extra[*]:-standard VA-API encoding}"
set +e
timeout -k 3s 45s runuser -u veyra -- env LIBVA_DRIVER_NAME=iHD \
  ffmpeg -hide_banner -benchmark -stats_period 2 -loglevel info -nostdin \
  -vaapi_device "$DEVICE" \
  -f lavfi -i 'testsrc2=size=1280x720:rate=25' \
  -frames:v 300 -an -vf 'format=nv12,hwupload' \
  -c:v h264_vaapi "${extra[@]}" -qp 23 -g 25 -bf 0 \
  -f h264 -y /dev/null > "$log" 2>&1
rc=$?
set -e
grep -E 'Driver version|frame=|speed=|bench:|Error|error|Assertion|Failed' "$log" | tail -24 || true
if (( rc != 0 )); then
  echo "FAIL: iHD hardware encode exited $rc; no services or global graphics settings altered."
  tail -15 "$log"
  exit 6
fi
echo 'PASS: iHD hardware H.264 encoding works using a process-local driver override.'
echo 'NOTE: This tests hardware ENCODING, not virtual Chrome decoding or display smoothness.'
