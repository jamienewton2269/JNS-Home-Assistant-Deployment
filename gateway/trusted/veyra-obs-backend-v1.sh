#!/usr/bin/env bash
# VEYRA OBS backend v1: safe OBS compatibility stage, no legacy media changes.
# Never recreate :92, modify Chrome, restart kiosk or run another ffmpeg process.
set -Eeuo pipefail
BASE=/opt/veyra/obs-backend-v1
USER_NAME=veyra
UID_VEYRA=$(id -u "$USER_NAME")
RUNTIME=/run/user/$UID_VEYRA
# Global because the EXIT trap runs after probe() local variables go out of scope.
xvfb_pid=""

audit() {
  echo "=== VEYRA OBS AUDIT ==="
  test -x /usr/bin/obs || { echo "BLOCKED: OBS missing"; return 2; }
  /usr/bin/obs --version
  for p in linux-capture.so linux-pulseaudio.so obs-websocket.so obs-ffmpeg.so; do
    test -f "/usr/lib/x86_64-linux-gnu/obs-plugins/$p" || { echo "BLOCKED: OBS plugin $p missing"; return 2; }
    echo "PLUGIN=$p"
  done
  for s in veyra-kiosk.service veyra-virtual-loopback-v01.service veyra-itvx-vnc-v01.service; do
    systemctl is-active --quiet "$s" || { echo "BLOCKED: Protected $s not running"; return 2; }
    echo "SERVICE=$s:active"
  done
  test -S /tmp/.X11-unix/X92 || { echo "BLOCKED: authenticated Chrome :92 absent"; return 2; }
  DISPLAY=:92 xdpyinfo 2>/dev/null | grep -F dimensions: || return 2
  for t in veyra-tv-v075.service veyra-tv-v079.service veyra-tv-v080.service; do
    if systemctl is-active --quiet "$t"; then echo "BLOCKED: previous media trial $t is active"; return 2; fi
  done
  echo "PASS: OBS installed and display available; audit changed nothing."
}
stage() {
  test "$EUID" -eq 0 || { echo "Use sudo"; return 2; }
  audit
  install -d -m 750 -o "$USER_NAME" -g "$USER_NAME" "$BASE"
  install -d -m 700 -o "$USER_NAME" -g "$USER_NAME" "$BASE/obs-config" "$BASE/probe-config"
  install -d -m 750 -o "$USER_NAME" -g "$USER_NAME" "$BASE/logs"
  cat > "$BASE/manifest.json" <<'JSON'
{
  "schema": "veyra.obs.backend/v1",
  "status": "staged-no-traffic",
  "capture": "OBS XSHM :92; PulseAudio monitor veyra_virtual_capture.monitor",
  "candidate_output": "local-only SRT; srt://127.0.0.1:23600?mode=listener&latency=150000",
  "video": "1366x768, use measured source-native cadence",
  "backend": "OBS Studio 30.2",
  "deprecated": "external FFmpeg and FFplay development",
  "preserve": ["Chrome profile", "Xvfb :92", "VNC", "kiosk", "dual-boot Windows"],
  "automatic_service_enable": false
}
JSON
  chmod 644 "$BASE/manifest.json"
  echo "STAGED: OBS workspace only; no service started, source switched or package installed."
}
# Only stop the known throwaway :93 process; never act on ITVX Xvfb :92.
# The X lock is the authoritative server PID, not the runuser wrapper PID.
recover_x93() {
  test "$EUID" -eq 0 || { echo "Use sudo for :93 recovery"; return 2; }
  if test ! -f /tmp/.X93-lock; then
    echo "RECOVERY: no :93 server lock; nothing to stop"
    return 0
  fi
  local pid proc_uid argv
  read -r pid < /tmp/.X93-lock || return 2
  [[ "$pid" =~ ^[0-9]+$ ]] || { echo "SAFETY STOP: malformed :93 lock PID"; return 2; }
  [[ -r "/proc/$pid/cmdline" ]] || { echo "SAFETY STOP: stale :93 lock; no process signalled"; return 2; }
  proc_uid=$(stat -c %u "/proc/$pid")
  argv=$(tr '\0' ' ' < "/proc/$pid/cmdline")
  if [[ "$proc_uid" != "$UID_VEYRA" ||
        "$argv" != '/usr/bin/Xvfb :93 -screen 0 1366x768x24 -nolisten tcp '* ]]; then
    echo "SAFETY STOP: process $pid does not match the isolated veyra Xvfb :93 command"
    return 2
  fi
  kill -TERM "$pid"
  # SIGTERM is asynchronous: wait for the verified :93 process to disappear.
  local n state
  for ((n=0; n<30; n++)); do
    if ! kill -0 "$pid" 2>/dev/null; then
      echo "RECOVERY VERIFIED: throwaway Xvfb :93 PID $pid has exited"
      return 0
    fi
    state=$(ps -o stat= -p "$pid" 2>/dev/null || true)
    if [[ "$state" == Z* ]]; then
      echo "RECOVERY VERIFIED: Xvfb :93 is terminated (waiting for parent to reap zombie)"
      return 0
    fi
    sleep 0.2
  done
  echo "WARNING: termination requested, but :93 process $pid has not exited after six seconds" >&2
  return 4
}

probe() {
  test "$EUID" -eq 0 || { echo "Use sudo"; return 2; }
  audit
  test -d "$BASE/probe-config" || { echo "Run stage first"; return 2; }
  test ! -S /tmp/.X11-unix/X93 && test ! -e /tmp/.X93-lock || {
    echo "BLOCKED: temporary test display :93 already occupied"; return 2;
  }
  test -d "$RUNTIME" || { echo "BLOCKED: veyra runtime missing"; return 2; }
  local rc
  runuser -u "$USER_NAME" -- /usr/bin/Xvfb :93 -screen 0 1366x768x24 -nolisten tcp \
    >"$BASE/logs/xvfb-probe.log" 2>&1 &
  xvfb_pid=$!
  # EXIT fires after probe() returns. xvfb_pid must remain global with set -u.
  # Terminate the verified server process before its runuser wrapper.
  trap 'recover_x93 || true; if [[ "$xvfb_pid" =~ ^[0-9]+$ ]]; then kill -TERM "$xvfb_pid" 2>/dev/null || true; wait "$xvfb_pid" 2>/dev/null || true; fi' EXIT
  sleep 2
  kill -0 "$xvfb_pid" 2>/dev/null || { echo "FAIL: isolated Xvfb could not start"; return 3; }
  runuser -u "$USER_NAME" -- env DISPLAY=:93 xdpyinfo >/dev/null 2>&1 || {
    echo "FAIL: virtual test screen not accessible"; return 3;
  }
  touch "$BASE/logs/obs-probe.log"
  chown "$USER_NAME:$USER_NAME" "$BASE/logs/obs-probe.log"
  set +e
  runuser -u "$USER_NAME" -- env DISPLAY=:93 QT_QPA_PLATFORM=xcb \
    XDG_CONFIG_HOME="$BASE/probe-config" XDG_RUNTIME_DIR="$RUNTIME" \
    timeout --signal=TERM -k 3s 14s dbus-run-session -- \
    /usr/bin/obs --multi --disable-shutdown-check --disable-updater --only-bundled-plugins \
    >"$BASE/logs/obs-probe.log" 2>&1
  rc=$?
  set -e
  echo "OBS_PROBE_EXIT=$rc (124 means a normal 14-second probe timeout)"
  grep -Ei 'OpenGL|renderer|graphics|loaded module|libEGL|failed|error|scene' \
    "$BASE/logs/obs-probe.log" | tail -30 || true
  if grep -Eiq 'Failed to initialize video|Failed to initialize graphics|OpenGL 3.[012] (not supported|required)' "$BASE/logs/obs-probe.log"; then
    echo "FAIL: OBS OpenGL startup incompatible with current virtual graphics"; return 4
  fi
  if grep -Eiq 'Mesa llvmpipe|softpipe|Software Rasterizer' "$BASE/logs/obs-probe.log"; then
    echo "BLOCKED: OBS uses software OpenGL (llvmpipe), not Intel GPU rendering."
    echo "Do not proceed to live OBS capture/restream on this Xvfb screen."
    return 6
  fi
  if test "$rc" -ne 0 && test "$rc" -ne 124; then
    echo "FAIL: OBS exited unexpectedly in the isolated graphics test"; return 5
  fi
  echo "PROBE COMPLETE: renderer did not identify itself as software; still requires performance and GPU verification."
}
case "$*" in
  audit) audit ;;
  stage) stage ;;
  recover) recover_x93 ;;
  probe) probe ;;
  status) audit; test ! -f "$BASE/manifest.json" || cat "$BASE/manifest.json"; test ! -f "$BASE/logs/obs-probe.log" || tail -20 "$BASE/logs/obs-probe.log" ;;
  *) echo "Usage: bash $0 audit | sudo bash $0 stage | sudo bash $0 recover | sudo bash $0 probe | bash $0 status"; exit 2 ;;
esac
