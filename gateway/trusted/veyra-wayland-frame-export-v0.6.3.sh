#!/usr/bin/env bash
# Veyra v0.6.3 — isolated GPU-Wayland animated frame capture proof.
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
echo '=== GPU VIRTUAL WAYLAND TEST v0.6.3 ==='
echo "Chrome: $CHROME"
echo "Cage: $(command -v cage)"
echo "Intel GPU: $(readlink -f /sys/class/drm/renderD128/device 2>/dev/null || echo present)"
echo 'Working services: physical Cage, virtual Chrome and VNC active'
echo 'Test backend: wlroots headless + GLES2 + renderD128 (no DRM modesetting)'
echo 'Cage uses its own automatically named Wayland socket (never the physical display).'
echo 'Test browser: isolated local animated test page with no provider credentials'
echo 'The running Chrome profile will NOT be opened or modified.'
echo 'Veyra capture test: Wayland screencopy PNG frames stay only in memory.'
if [[ "$mode" == preflight ]]; then
 echo 'PREFLIGHT COMPLETE — no processes started or configuration changed.'
 exit 0
fi
command -v setsid >/dev/null
dir=$(mktemp -d /tmp/veyra-headless-v063.XXXXXXXX)
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
command -v python3 >/dev/null || { echo 'Python 3 unavailable'; exit 3; }
command -v dpkg-deb >/dev/null || { echo 'dpkg-deb unavailable'; exit 3; }
GRIM=$(command -v grim || true)
if [[ -z "$GRIM" ]]; then
  echo 'Staging grim screencopy client from configured Debian apt repositories (not installing).'
  (cd "$dir" && apt-get -qq download grim) || { echo 'Cannot download grim from existing apt sources'; exit 4; }
  deb=$(find "$dir" -maxdepth 1 -type f -name 'grim_*.deb' -print -quit)
  [[ -n "$deb" ]] || { echo 'Debian grim download not found'; exit 4; }
  mkdir -p "$dir/debian-staged"
  dpkg-deb -x "$deb" "$dir/debian-staged"
  GRIM="$dir/debian-staged/usr/bin/grim"
  [[ -x "$GRIM" ]] || { echo 'Staged grim executable missing'; exit 4; }
  if ldd "$GRIM" | grep -q 'not found'; then
    echo 'grim depends on a missing runtime library; no packages installed.'
    ldd "$GRIM" | grep 'not found' || true
    exit 4
  fi
fi
echo "Screencopy utility: $GRIM"
cat >"$dir/probe.html" <<'HTML'
<!doctype html>
<html lang="en"><meta charset="utf-8"/>
<title>Veyra virtual GPU rendering test</title>
<style>
html,body{margin:0;width:100%;height:100%;overflow:hidden;background:#07192b;color:white;font:28px sans-serif}
h1{margin:32px}
#panel{position:absolute;left:0;right:0;top:140px;height:230px;overflow:hidden;
background:repeating-linear-gradient(90deg,#123b66 0 35px,#214a62 35px 70px)}
#bar{position:absolute;top:20px;width:190px;height:190px;border-radius:24px;
background:linear-gradient(30deg,#fae450,#e95835);animation:move 3.7s linear infinite alternate}
@keyframes move{from{transform:translateX(8px)}to{transform:translateX(1100px)}}
#marker{position:absolute;top:440px;left:32px;font:22px monospace;}
</style>
<h1>VEYRA GPU WAYLAND — ISOLATED TEST</h1>
<div id="panel"><div id="bar"></div></div>
<div id="marker">A local animated page, not an ITVX stream</div>
</html>
HTML
chmod 644 "$dir/probe.html"

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
 --disable-background-timer-throttling --disable-renderer-backgrounding \
 --window-size=1366,768 --start-fullscreen \
 "file://$dir/probe.html" >"$log" 2>&1 &
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
echo '=== Wayland frame export (3 in-memory screenshots) ==='
if runuser -u veyra -- env -u DISPLAY \
  XDG_RUNTIME_DIR="$dir/runtime" WAYLAND_DISPLAY="$socket" \
  python3 - "$GRIM" <<'PY'
import hashlib, struct, subprocess, sys, time
tool = sys.argv[1]
frames = []
for sample in range(3):
    try:
        p = subprocess.run([tool, '-t', 'png', '-'], capture_output=True, timeout=12)
    except subprocess.TimeoutExpired:
        print(f'FAIL: frame {sample+1} timed out')
        sys.exit(4)
    if p.returncode != 0:
        print(f'FAIL: screencopy frame {sample+1}, exit {p.returncode}')
        print(p.stderr.decode(errors='replace')[-1000:])
        sys.exit(4)
    raw = p.stdout
    if len(raw)<40 or not raw.startswith(b'\x89PNG\r\n\x1a\n'):
        print('FAIL: invalid PNG frame from Wayland screencopy')
        sys.exit(4)
    width,height=struct.unpack('>II',raw[16:24])
    if width<32 or height<32:
        print('FAIL: frame dimensions are implausible')
        sys.exit(4)
    digest=hashlib.sha256(raw).hexdigest()
    frames.append(digest)
    print(f'Captured frame {sample+1}: {width}x{height}, {len(raw)} compressed bytes, SHA256={digest[:14]}')
    time.sleep(.64)
if len(set(frames))>=2:
    print('PASS: real rendered frames exported from isolated Wayland display.')
    print('PASS: animation changed between captures.')
else:
    print('CHECK: successful frame export, but captured images remained identical.')
    print('The Chrome page or animation may have stalled; dynamic rendering not proved.')
    sys.exit(5)
PY
then
  echo 'PASS: Wayland capture proof succeeded. No frames written to disk.'
else
  echo 'FAIL: isolated Wayland screencopy. Chrome/Wayland startup is still verified.'
  exit 8
fi
echo '=== Findings ==='
echo 'Separate compositor and blank Chrome completed startup interval if the above checks passed.'
echo 'This tests graphics plumbing: NOT ITVX decode or native-quality playback.'
echo 'No provider credentials or programme media used. No captured frames retained.'
