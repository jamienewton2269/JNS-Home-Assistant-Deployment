#!/usr/bin/env bash
# Veyra v0.6.2.3 — independent virtual Wayland GPU browser proof.
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
CHROME_SOURCE=''
# Find the binary actually running Veyra's existing isolated Chrome.
# Reading /proc does NOT communicate with, signal, restart or modify Chrome.
for task in /proc/[0-9]*; do
  pid=${task##*/}
  [[ -r "$task/cmdline" ]] || continue
  [[ "$(stat -c %u "$task" 2>/dev/null || true)" == "$(id -u veyra)" ]] || continue
  exe=$(readlink -f "$task/exe" 2>/dev/null || true)
  [[ -n "$exe" && -x "$exe" ]] || continue
  case "$(basename "$exe")" in
    chrome|chromium|chromium-browser) ;;
    *) continue ;;
  esac
  # Only match the MAIN Chrome process with Veyra's dedicated virtual profile.
  if tr '\0' '\n' <"$task/cmdline" |
      grep -Eq '^--type='; then
    continue
  fi
  if tr '\0' '\n' <"$task/cmdline" |
      grep -Fq '/opt/veyra/virtual-loopback-v01/profile'; then
    CHROME="$exe"
    CHROME_SOURCE="running Veyra virtual Chrome, PID $pid"
    break
  fi
done
# Fallback for systems whose Chrome wrapper is not directly a browser binary.
if [[ -z "$CHROME" ]]; then
  for app in google-chrome-stable google-chrome chromium chromium-browser; do
    if command -v "$app" >/dev/null 2>&1; then
      CHROME=$(command -v "$app")
      CHROME_SOURCE="PATH: $app"
      break
    fi
  done
fi
if [[ -z "$CHROME" ]]; then
  for app in \
    /opt/google/chrome/chrome \
    /usr/lib/chromium/chromium \
    /usr/lib/chromium-browser/chromium-browser \
    /opt/veyra/chrome/chrome \
    /opt/veyra/chromium/chrome; do
    if [[ -x "$app" ]]; then
      CHROME="$app"
      CHROME_SOURCE="known executable path"
      break
    fi
  done
fi
[[ -n "$CHROME" && -x "$CHROME" ]] || {
  echo 'Unable to discover running Veyra Chrome executable.'
  echo 'No processes or services changed.'
  echo 'Inspect Chrome processes with: ps -eo user,pid,comm,args | grep -E "[c]hrome|[c]hromium"'
  exit 3
}
echo "Chrome discovered from: $CHROME_SOURCE"
[[ -c /dev/dri/renderD128 ]] || { echo "Intel GPU render node missing"; exit 3; }
VUID=$(id -u veyra)
[[ -d /run/user/$VUID ]] || { echo "veyra runtime missing"; exit 3; }
echo '=== GPU VIRTUAL WAYLAND TEST v0.6.2.3 ==='
echo "Chrome: $CHROME"
echo "Cage: $(command -v cage)"
echo "Intel GPU: $(readlink -f /sys/class/drm/renderD128/device 2>/dev/null || echo present)"
echo 'Working services: physical Cage, virtual Chrome and VNC active'
echo 'Test backend: wlroots headless + GLES2 + renderD128 (no DRM modesetting)'
echo 'Cage uses its own automatically named Wayland socket (never the physical display).'
echo 'Test browser: isolated temporary profile opening about:blank'
echo 'The running Chrome profile will NOT be opened or modified.'
if [[ "$mode" == preflight ]]; then
 echo 'PREFLIGHT COMPLETE — no processes started or configuration changed.'
 exit 0
fi
command -v setsid >/dev/null
dir=$(mktemp -d /tmp/veyra-headless-v0623.XXXXXXXX)
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
 -u DISPLAY -u WAYLAND_DISPLAY -u WAYLAND_SOCKET -u _WAYLAND_DISPLAY -u DBUS_SESSION_BUS_ADDRESS \
 XDG_RUNTIME_DIR="$dir/runtime" XDG_SESSION_TYPE=wayland \
 WLR_BACKENDS=headless WLR_HEADLESS_OUTPUTS=1 \
 WLR_LIBINPUT_NO_DEVICES=1 WLR_RENDERER=gles2 \
 WLR_RENDER_DRM_DEVICE=/dev/dri/renderD128 \
 LIBGL_ALWAYS_SOFTWARE=0 \
 cage -- "$CHROME" \
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
socket=''
for n in $(seq 1 60); do
 socket=$(find "$dir/runtime" -maxdepth 1 -type s -name 'wayland-*' -printf '%f\n' 2>/dev/null | head -1 || true)
 if [[ -n "$socket" && -S "$dir/runtime/$socket" ]]; then ok=1; break; fi
 if ! kill -0 "$p" 2>/dev/null; then break; fi
 sleep .2
done
if (( !ok )); then
 echo 'FAIL: no Wayland socket was created in the isolated runtime directory.'
 echo '=== Test output ==='
 tail -65 "$log"
 exit 6
fi
echo "PASS: isolated Cage compositor is listening on $dir/runtime/$socket"
echo 'This is NOT the physical Cage display.'
sleep 8
if ! kill -0 "$p" 2>/dev/null; then
 echo 'Cage wrapper exited during Chrome startup.'
 tail -65 "$log"
 exit 7
fi
if ! find "$dir/runtime" -maxdepth 1 -type s -name 'wayland-*' -print -quit | grep -q .; then
 echo 'FAIL: isolated compositor socket disappeared during Chrome startup.'
 tail -65 "$log"
 exit 7
fi
echo '=== Isolated test processes ==='
ps -eo pid,pgid,comm,args | awk -v pg="$pg" '$2==pg {print substr($0,1,170)}' | head -26 || true
echo '=== Renderer/device evidence ==='
foundgpu=0
foundcage=0
cgpu=0
while read -r pid grp comm args; do
 [[ "$grp" == "$pg" ]] || continue
 if [[ "$comm" == cage ]]; then
   foundcage=1
   echo "Cage compositor PID: $pid"
   if find "/proc/$pid/fd" -maxdepth 1 -type l -printf '%l\n' 2>/dev/null | grep -Eq '^/dev/dri/(renderD128|card0)$'; then
     echo 'PASS: headless Cage compositor holds Intel GPU device.'
     cgpu=1
   else
     echo 'CHECK: headless Cage compositor GPU device FD not observed.'
   fi
 fi
 if [[ "$args" == *--type=gpu-process* && "$comm" == chrome ]]; then
   foundgpu=1
   echo "Chrome GPU subprocess PID: $pid"
   if find "/proc/$pid/fd" -maxdepth 1 -type l -printf '%l\n' 2>/dev/null | grep -Eq '^/dev/dri/(renderD128|card0)$'; then
     echo 'PASS: Chrome GPU process holds Intel GPU device.'
   else
     echo 'CHECK: Chrome GPU process exists; no Intel GPU fd observed.'
   fi
 fi
done < <(ps -eo pid,pgid,comm,args --no-headers)
(( foundcage )) || echo 'CHECK: compositor process not found in test process group.'
(( foundgpu )) || echo 'CHECK: Chrome GPU subprocess not found in test process group.'
echo "Renderer FD observed: $cgpu (1=yes, 0=not observed)"
echo '=== Software rasterizer indicators ==='
if grep -Eiq 'llvmpipe|softpipe|software rasterizer' "$log"; then
 echo 'WARNING: software rasterizer mentioned in logs.'
else
 echo 'No software rasterizer warnings in this startup log (not proof of full GPU acceleration).'
fi
echo '=== Relevant compositor/Chrome messages ==='
grep -Ei 'gles2|egl|render|drm|gpu|wayland|llvmpipe|software|failed|error' "$log" | tail -48 || true
if grep -Eiq 'llvmpipe|softpipe|software rasterizer' "$log"; then
 echo 'WARNING: software rasterizer appeared in logs; native GPU rendering not proved.'
fi
echo '=== Findings ==='
echo 'Separate compositor and blank Chrome completed startup interval if the above checks passed.'
echo 'This tests graphics plumbing: NOT ITVX decode or native-quality playback.'
echo 'No provider credentials or programme media used.'
