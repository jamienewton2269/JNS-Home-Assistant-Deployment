#!/usr/bin/env bash
# VEYRA v0.6.0 isolated Intel iHD video driver evaluation.
# Packages downloaded/extracted to /tmp, never installed into system paths.
set -Eeuo pipefail
export LC_ALL=C
[[ $EUID -eq 0 ]] || { echo 'Use sudo';exit 2; }
mode="${1:-check}"
[[ "$mode" == check || "$mode" == test ]] || { echo "Usage: sudo bash $0 {check|test}";exit 2; }
for name in apt-cache apt-get dpkg-deb ffmpeg vainfo runuser timeout ldd; do
  command -v "$name" >/dev/null || { echo "Missing command $name";exit 2; }
done
[[ -c /dev/dri/renderD128 ]] || { echo 'No Intel render node'; exit 2; }
id veyra >/dev/null
candidate=$(apt-cache policy intel-media-va-driver | sed -n 's/^  Candidate: //p' | head -1)
[[ -n "$candidate" && "$candidate" != "(none)" ]] || {
  echo 'Driver unavailable in existing apt sources'; apt-cache policy intel-media-va-driver; exit 3;
}
echo "Driver candidate: intel-media-va-driver $candidate"
echo 'Existing services (will not be restarted):'
for service in veyra-kiosk.service veyra-virtual-loopback-v01.service veyra-itvx-vnc-v01.service; do
 echo "$service: $(systemctl is-active "$service" 2>/dev/null || true)"
done
work=$(mktemp -d /tmp/veyra-ihd-v060.XXXXXXXX)
trap 'rm -rf -- "$work"' EXIT
chmod 755 "$work"
mkdir -m 755 "$work/extract"
fetch() {
  local name="$1" deb actual
  echo "Downloading $name from existing Debian apt sources (not installing)"
  (cd "$work" && apt-get -qq download "$name") || { echo "Cannot download $name";return 4; }
  deb=$(find "$work" -maxdepth 1 -type f -name "${name}_*.deb" -print -quit)
  [[ -n "$deb" ]] || { echo "Package missing: $name";return 4; }
  actual=$(dpkg-deb --field "$deb" Package)
  [[ "$actual" == "$name" ]] || { echo "Package mismatch: $actual";return 4; }
  dpkg-deb -x "$deb" "$work/extract"
}
fetch intel-media-va-driver
if ! dpkg-query -W -f='${Status}' libigdgmm12 2>/dev/null | grep -Fxq 'install ok installed'; then
  echo 'Staging missing libigdgmm12 runtime dependency locally'
  fetch libigdgmm12
fi
driver=$(find "$work/extract" -type f -name iHD_drv_video.so -print -quit)
[[ -n "$driver" ]] || { echo 'No iHD shared library in package';exit 5; }
dir=$(dirname "$driver")
libs="$work/extract/usr/lib/x86_64-linux-gnu"
chmod -R a+rX "$work/extract"
missing=$(LD_LIBRARY_PATH="$libs" ldd "$driver" | grep 'not found' || true)
if [[ -n "$missing" ]]; then echo "Driver libraries missing: $missing";exit 5; fi
echo '=== Intel iHD VA-API probe (process-only override) ==='
probe="$work/vainfo.log"
if ! timeout -k 2s 15s runuser -u veyra -- env \
 LIBVA_DRIVER_NAME=iHD LIBVA_DRIVERS_PATH="$dir" LD_LIBRARY_PATH="$libs" \
 vainfo --display drm --device /dev/dri/renderD128 >"$probe" 2>&1; then
 tail -28 "$probe"; echo 'FAIL: isolated iHD init';exit 6
fi
grep -E 'Driver version|VAProfileH264|VA-API version|VAEntrypointEncSlice' "$probe" | head -32 || true
if [[ "$mode" == check ]]; then echo "PASS: isolated iHD initialization; to benchmark, run sudo bash $0 test";exit 0;fi
if ! grep -Eq 'VAProfileH264(High|Main)[[:space:]]*:[[:space:]]*VAEntrypointEncSlice(LP)?' "$probe"; then
 echo 'No H264 encoder advertised; refusing test';exit 7
fi
extra=()
if ! grep -Eq 'VAProfileH264(High|Main)[[:space:]]*:[[:space:]]*VAEntrypointEncSlice[[:space:]]*$' "$probe"; then
 extra=(-low_power 1)
fi
echo '=== Intel iHD 720p25 300 synthetic frame encoding benchmark ==='
log="$work/encode.log"
if ! timeout -k 3s 45s runuser -u veyra -- env \
 LIBVA_DRIVER_NAME=iHD LIBVA_DRIVERS_PATH="$dir" LD_LIBRARY_PATH="$libs" \
 ffmpeg -hide_banner -benchmark -stats_period 2 -loglevel info -nostdin \
 -vaapi_device /dev/dri/renderD128 \
 -f lavfi -i 'testsrc2=size=1280x720:rate=25' \
 -frames:v 300 -an -vf 'format=nv12,hwupload' \
 -c:v h264_vaapi "${extra[@]}" -qp 23 -g 25 -bf 0 \
 -f h264 -y /dev/null >"$log" 2>&1; then
 tail -35 "$log";echo 'FAIL: isolated iHD encode. Existing sessions untouched.';exit 8
fi
grep -E 'frame=|speed=|bench:' "$log" | tail -12 || true
echo 'PASS: isolated Intel iHD encoder works.'
echo 'No packages installed; no video/audio saved; no services restarted.'
