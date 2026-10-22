#!/usr/bin/env bash
# Veyra v0.6.2 — independent virtual Wayland GPU browser proof.
# Separate ephemeral Chrome profile. NO ITVX login or programme playback.
# Does NOT stop/restart Chrome :92, VNC, Cage tty1, or existing buffer.
set -Eeuo pipefail
[[ $EUID == 0 ]] || { echo 'Run with sudo'; exit 2; }
mode="${1:-preflight}"
[[ "$mode" == preflight || "$mode" == probe ]] || {
 echo "Usage: sudo bash $0 {preflight|probe}"; exit 2;
}
CAP=veyra-virtual-loopback-v01.service
VNC=veyra-itvx-vnc-v01.service
KIOSK=veyra-kiosk.service
for u in "$CAP" "$VNC" "$KIOSK"; do
 systemctl is-active --quiet "$u" || { echo "SAFETY STOP: $u inactive"; exit 2; }
done
command -v cage >/dev/null || { echo 'cage compositor not installed'; exit 3; }
CHROME=''
for app in google-chrome-stable google-chrome chromium chromium-browser; do
 if command -v "$app" >/dev/null 2>&1; then CHROME=$(command -v "$app"); break; fi
done
[[ -n "$CHROME" ]] || {
 if [[ -x /opt/google/chrome/chrome ]]; then CHROME=/opt/google/chrome/chrome
 else echo 'Chrome executable not found'; exit 3; fi
}
[[ -c /dev/dri/renderD128 ]] || { echo "Intel GPU render node missing"; exit 3; }
VUID=$(id -u veyra)
[[ -d /run/user/$VUID ]] || { echo "veyra runtime missing"; exit 3; }
echo '=== GPU VIRTUAL WAYLAND TEST v0.6.2 ==='
echo "Chrome: $CHROME"
echo "Cage: $(command -v cage)"
echo "Intel GPU: $(readlink -f /sys/class/drm/renderD128/device 2>/dev/null || echo present)"
echo 'Working services: physical Cage, virtual Chrome and VNC active'
echo 'Test backend: wlroots headless + GLES2 + renderD128 (no DRM modesetting)'
echo 'Test browser: isolated temporary profile opening about:blank'
if [[ "$mode" == preflight ]]; then
 echo 'PREFLIGHT COMPLETE — no processes started or configuration changed.'
 exit 0
fi
command -v setsid >/dev/null
dir=$(mktemp -d /tmp/veyra-headless-v062.XXXXXXXX)
mkdir -m 700 "$dir/runtime" "$dir/profile"
chown -R veyra:veyra "$dir"
log="$dir/wayland.log"
touch "$log"
chown veyra:veyra "$log"
p=''
pg=''
cleanup() {
 rc=$?
 trap - EXIT INT TERM
 set +e
 if [[ -n "$pg" && "$pg" =~ ^[0-9]+$ && "$pg" != "$(ps -o pgid= -p $$ | tr -d ' ')" ]]; then
   kill -TERM -- "-$pg" 2>/dev/null || true
   sleep 1
   kill -KILL -- "-$pg" 2>/dev/null || true
 elif [[ -n "$p" && "$p" =~ ^[0-9]+$ ]]; then
   kill -TERM "$p" 2>/dev/null || true
 fi
 [[ -n "$p" ]] && wait "$p" 2>/dev/null || true
 rm -rf -- "$dir"
 echo "Cleanup complete: ephemeral Wayland and browser test removed."
 echo "Services: kiosk=$(systemctl is-active "$KIOSK" 2>/dev/null || true), capture=$(systemctl is-active "$CAP" 2>/dev/null || true), VNC=$(systemctl is-active "$VNC" 2>/dev/null || true)"
 exit "$rc"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
# Clear display environment: must never attach to real Cage or Xvfb.
# Headless wlroots backend will not claim the physical monitor/change its mode.
setsid runuser -u veyra -- env \
 -u DISPLAY -u DBUS_SESSION_BUS_ADDRESS \
 XDG_RUNTIME_DIR="$dir/runtime" XDG_SESSION_TYPE=wayland \
 WAYLAND_DISPLAY=veyra-native-test \
 WLR_BACKENDS=headless WLR_HEADLESS_OUTPUTS=1 \
 WLR_LIBINPUT_NO_DEVICES=1 WLR_RENDERER=gles2 \
 WLR_RENDER_DRM_DEVICE=/dev/dri/renderD128 \
 LIBGL_ALWAYS_SOFTWARE=0 \
 cage -D -- "$CHROME" \
 --ozone-platform=wayland \
 --user-data-dir="$dir/profile" \
 --no-first-run --no-default-browser-check --disable-sync \
 --disable-background-networking --disable-extensions \
 --window-size=1366,768 --start-fullscreen \
 about:blank >"$log" 2>&1 &
p=$!
pg=$(ps -o pgid= -p "$p" | tr -d ' ')
[[ -n "$pg" ]] || { echo 'Unable to establish isolated process group'; exit 5; }
ok=0
for n in $(seq 1 60); do
 if [[ -S "$dir/runtime/veyra-native-test" ]]; then ok=1; break; fi
 if ! kill -0 "$p" 2>/dev/null; then break; fi
 sleep .2
done
if (( !ok )); then
 echo 'Headless compositor did not create its isolated Wayland socket.'
 echo '=== Compositor diagnostics ==='
 tail -65 "$log"
 exit 6
fi
echo 'PASS: separate headless Wayland display is online.'
sleep 8
if ! kill -0 "$p" 2>/dev/null; then
 echo 'Compositor exited during Chrome startup.'
 tail -65 "$log"
 exit 7
fi
echo '=== Test process group ==='
ps -eo pid,pgid,comm,args | awk -v pg="$pg" '$2==pg {print substr($0,1,180)}' | head -28
echo '=== Chromium GPU render-device access ==='
foundgpu=0
while read -r pid grp comm args; do
 [[ "$grp" == "$pg" && "$args" == *--type=gpu-process* ]] || continue
 foundgpu=1
 echo "Chrome GPU subprocess PID: $pid"
 if ls -l "/proc/$pid/fd" 2>/dev/null | grep -qE '/dev/dri/(renderD128|card0)'; then
   echo 'PASS: GPU subprocess has an Intel DRM device open.'
 else
   echo 'CHECK: GPU process detected, but no direct DRM fd shown.'
 fi
done < <(ps -eo pid,pgid,comm,args --no-headers)
(( foundgpu )) || echo 'CHECK: GPU process not identified; inspect log below.'
echo '=== Relevant compositor/Chrome messages ==='
grep -Ei 'gles2|egl|render|drm|gpu|wayland|llvmpipe|software|failed|error' "$log" | tail -48 || true
if grep -Eiq 'llvmpipe|softpipe|software rasterizer' "$log"; then
 echo 'WARNING: software rasterizer appeared in logs; native GPU rendering not proved.'
fi
echo '=== Findings ==='
echo 'Separate compositor and blank Chrome completed startup interval.'
echo 'This tests graphics plumbing: NOT ITVX decode or native-quality playback.'
echo 'No provider credentials or programme media used.'
