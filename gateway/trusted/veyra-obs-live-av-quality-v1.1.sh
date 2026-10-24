#!/usr/bin/env bash
# VEYRA OBS QA v1.1: 30-second native OBS picture+sound MKV and localhost SRT.
# Authenticated ITVX remains on Xvfb :92; OBS gets dedicated temporary :93.
# Never install packages, recreate :92, restart Chrome/VNC/Cage, or use FFplay.
set -Eeuo pipefail
BASE=/opt/veyra/obs-backend-v1/av-qa-v11
CFG=$BASE/config
OUT=$BASE/buffer
RUNTIME=/run/user/999
REC=/run/veyra-obs-av-v11.recovery
orig=''
xp=''
op=''
mp=''
timer=''
clean() {
  local rc=$?
  trap - EXIT INT TERM
  set +e
  for p in "$mp" "$op" "$xp"; do
    if [[ "$p" =~ ^[0-9]+$ ]]; then kill -TERM -- "-$p" 2>/dev/null || true; fi
  done
  sleep 2
  for p in "$mp" "$op" "$xp"; do
    if [[ "$p" =~ ^[0-9]+$ ]]; then kill -KILL -- "-$p" 2>/dev/null || true; wait "$p" 2>/dev/null || true; fi
  done
  # Xvfb server is a runuser child, not necessarily its wrapper PID.
  if [[ -r /tmp/.X93-lock ]]; then
    local p cmd owner
    read -r p < /tmp/.X93-lock || true
    if [[ "$p" =~ ^[0-9]+$ && -r "/proc/$p/cmdline" ]]; then
      cmd=$(tr '\0' ' ' < "/proc/$p/cmdline")
      owner=$(stat -c %u "/proc/$p")
      if [[ "$owner" == 999 && "$cmd" == *"/usr/bin/Xvfb :93 -screen 0 1366x768x24 -nolisten tcp"* ]]; then kill -TERM "$p" 2>/dev/null || true; fi
    fi
  fi
  if [[ "$orig" =~ ^[0-9]+$ && -f "$REC" ]]; then
    if [[ -r "/proc/$orig/cmdline" ]] && tr '\0' ' ' < "/proc/$orig/cmdline" | grep -Fq 'x11grab'; then
      kill -CONT "$orig" 2>/dev/null && rm -f "$REC" && echo "RESTORED ORIGINAL RECORDER $orig"
    fi
  fi
  if [[ -n "$timer" ]]; then systemctl stop "$timer.timer" 2>/dev/null || true; fi
  echo "OBS trial ended; original ITVX services preserved."
  exit "$rc"
}
check() {
  [[ "$EUID" == 0 ]] || { echo "Run with sudo"; return 2; }
  for c in obs mpv Xvfb python3 ffprobe pactl xdpyinfo systemd-run; do
    command -v "$c" >/dev/null || { echo "BLOCKED: $c missing"; return 2; }
  done
  for u in veyra-kiosk.service veyra-virtual-loopback-v01.service veyra-itvx-vnc-v01.service; do
    systemctl is-active --quiet "$u" || { echo "BLOCKED: $u inactive"; return 2; }
  done
  [[ -S /tmp/.X11-unix/X92 && -S "$RUNTIME/pulse/native" ]] || { echo "BLOCKED: ITVX capture source unavailable"; return 2; }
  [[ ! -e /tmp/.X93-lock && ! -S /tmp/.X11-unix/X93 ]] || { echo "BLOCKED: :93 occupied"; return 2; }
  [[ ! -e "$REC" ]] || { echo "BLOCKED: unresolved recorder recovery marker"; return 2; }
  for u in veyra-tv-v079.service veyra-tv-v080.service; do
    if systemctl is-active --quiet "$u"; then echo "BLOCKED: other display trial active"; return 2; fi
  done
  runuser -u veyra -- env XDG_RUNTIME_DIR="$RUNTIME" PULSE_SERVER="unix:$RUNTIME/pulse/native" pactl list short sources | grep -Fq veyra_virtual_capture.monitor || {
    echo "BLOCKED: ITVX audio capture monitor not found"; return 2;
  }
  echo "PASS: ITVX, Pulse audio, OBS, mpv, Cage, VNC available."
}
stage() {
  check
  install -d -m 750 -o veyra -g veyra "$BASE" "$OUT" "$BASE/logs"
  install -d -m 700 -o veyra -g veyra "$CFG"
  if find "$OUT" -maxdepth 1 -type f -name '*.mkv' | grep -q .; then
    echo "BLOCKED: existing quality buffer would be retained; move/review it first."; return 2
  fi
  python3 - "$CFG" "$OUT" <<'PY'
import pathlib,json,uuid,sys
root=pathlib.Path(sys.argv[1])/'obs-studio'
out=pathlib.Path(sys.argv[2])
scenes=root/'basic/scenes'
profile=root/'basic/profiles/VEYRA_QA'
scenes.mkdir(parents=True,exist_ok=True)
profile.mkdir(parents=True,exist_ok=True)
new=lambda:str(uuid.uuid4())
sn,vn,an=new(),new(),new()
v={"name":"ITVX XSHM :92","uuid":vn,"id":"xshm_input_v2","versioned_id":"xshm_input_v2","settings":{"advanced":True,"server":":92","screen":0,"show_cursor":False},"mixers":0}
a={"name":"ITVX monitor audio","uuid":an,"id":"pulse_output_capture","versioned_id":"pulse_output_capture","settings":{"device_id":"veyra_virtual_capture.monitor"},"mixers":1}
def i(src,ident):
 return {"name":src["name"],"source_uuid":src["uuid"],"id":ident,"visible":True,"locked":True,"pos":{"x":0,"y":0},"scale":{"x":1,"y":1},"rot":0,"align":5,"bounds_type":0}
scene={"name":"ITVX Quality","uuid":sn,"id":"scene","versioned_id":"scene","settings":{"items":[i(v,1),i(a,2)],"id_counter":3}}
data={"name":"VEYRA_QA","current_scene":"ITVX Quality","current_program_scene":"ITVX Quality",
"scene_order":[{"name":"ITVX Quality"}],"sources":[scene,v,a],"groups":[],
"transitions":[],"quick_transitions":[],"current_transition":"Cut","transition_duration":0,
"resolution":{"x":1366,"y":768},"version":2}
(scenes/'VEYRA_QA.json').write_text(json.dumps(data,indent=2))
(root/'user.ini').write_text("[General]\nFirstRun=true\nConfirmOnExit=false\n[Basic]\nProfile=VEYRA_QA\nProfileDir=VEYRA_QA\nSceneCollection=VEYRA_QA\nSceneCollectionFile=VEYRA_QA\n[BasicWindow]\nPreviewEnabled=false\n")
(profile/'basic.ini').write_text(
"[General]\nName=VEYRA_QA\n[Video]\nBaseCX=1366\nBaseCY=768\nOutputCX=1366\nOutputCY=768\nFPSType=1\nFPSInt=25\nScaleType=bicubic\nColorFormat=NV12\nColorSpace=709\nColorRange=Partial\n"
"[Audio]\nSampleRate=48000\nChannelSetup=Stereo\n[Output]\nMode=Simple\n"
"[SimpleOutput]\nFilePath="+str(out)+"\nRecFormat2=mkv\nRecQuality=Stream\n"
"StreamEncoder=x264\nRecEncoder=x264\nVBitrate=6500\nABitrate=160\n"
"Preset=ultrafast\nUseAdvanced=true\nx264Settings=keyint=50\n")
(profile/'service.json').write_text(json.dumps({"type":"rtmp_custom","settings":{
"server":"srt://127.0.0.1:23619?mode=listener&latency=200000","key":"","use_auth":False}},indent=2))
PY
  chown -R veyra:veyra "$BASE"
  echo "STAGED OBS: 1366x768 25fps, 6.5Mbps, AAC audio; private :93 and localhost SRT :23619."
}
findrecorder() {
  local cg p name commandline
  cg=$(systemctl show -p ControlGroup --value veyra-virtual-loopback-v01.service)
  [[ -n "$cg" && -d "/sys/fs/cgroup$cg" ]] || { echo "BLOCKED: recorder control group missing"; return 2; }
  local n=0
  while read -r p; do
    [[ "$p" =~ ^[0-9]+$ && -r "/proc/$p/comm" ]] || continue
    read -r name < "/proc/$p/comm" || true
    if [[ "$name" == ffmpeg ]]; then
      commandline=$(tr '\0' ' ' < "/proc/$p/cmdline")
      [[ "$commandline" == *x11grab* && "$commandline" == *:92* ]] || { echo "BLOCKED: unknown recorder process"; return 2; }
      orig="$p"; n=$((n+1))
    fi
  done < <(find "/sys/fs/cgroup$cg" -name cgroup.procs -exec cat {} + | sort -un)
  [[ "$n" == 1 ]] || { echo "BLOCKED: expected one recorder, found $n"; return 2; }
}
run_test() {
  stage
  findrecorder
  local socket sink
  socket=$(find "$RUNTIME" -maxdepth 1 -type s -name 'wayland-*' -printf '%f\n' | sort | head -1)
  [[ -n "$socket" ]] || { echo "BLOCKED: physical Wayland display socket not found"; return 2; }
  sink=$(runuser -u veyra -- env XDG_RUNTIME_DIR="$RUNTIME" PULSE_SERVER="unix:$RUNTIME/pulse/native" pactl list short sinks | awk '$2~/^alsa_output/ {print $2;exit}')
  [[ -n "$sink" ]] || { echo "BLOCKED: physical audio device not found"; return 2; }
  trap clean EXIT
  trap 'exit 130' INT
  trap 'exit 0' TERM
  setsid runuser -u veyra -- /usr/bin/Xvfb :93 -screen 0 1366x768x24 -nolisten tcp >"$BASE/logs/xvfb.log" 2>&1 &
  xp=$!
  sleep 2
  [[ -S /tmp/.X11-unix/X93 ]] || { echo "FAIL: independent :93 failed"; return 3; }
  timer="veyra-obs-av-resume-$(date +%s)-$$"
  systemd-run --quiet --collect --unit="$timer" --on-active=95s \
    /usr/bin/bash -c 'p="$1"; marker="$2"; if test -f "$marker" && test -r "/proc/$p/cmdline" && tr "\0" " " < "/proc/$p/cmdline" | grep -Fq "x11grab"; then kill -CONT "$p"; rm -f "$marker"; fi' \
    _ "$orig" "$REC"
  printf '%s\n' "$orig" > "$REC"
  chmod 600 "$REC"
  kill -STOP "$orig"
  echo "OBS QA START: original recorder paused; independent 95-second recovery armed."
  setsid runuser -u veyra -- env DISPLAY=:93 QT_QPA_PLATFORM=xcb \
    XDG_CONFIG_HOME="$CFG" XDG_RUNTIME_DIR="$RUNTIME" \
    PULSE_SERVER="unix:$RUNTIME/pulse/native" \
    /usr/bin/obs --multi --only-bundled-plugins --disable-updater --disable-shutdown-check \
      --disable-missing-files-check --profile VEYRA_QA --collection VEYRA_QA \
      --scene "ITVX Quality" --startrecording --startstreaming \
    >"$BASE/logs/obs-console.log" 2>&1 &
  op=$!
  sleep 6
  kill -0 "$op" 2>/dev/null || { echo "FAIL: OBS exited before capture"; tail -30 "$BASE/logs/obs-console.log"; return 4; }
  setsid runuser -u veyra -- env XDG_RUNTIME_DIR="$RUNTIME" WAYLAND_DISPLAY="$socket" \
    PULSE_SERVER="unix:$RUNTIME/pulse/native" PULSE_SINK="$sink" LIBVA_DRIVER_NAME=i965 \
    timeout -k 2s 24s mpv --no-config --fullscreen --no-border \
      --vo=gpu --gpu-context=wayland --hwdec=vaapi --ao=pulse \
      --demuxer-lavf-format=mpegts \
      'srt://127.0.0.1:23619?mode=caller&latency=200000' \
    >"$BASE/logs/mpv.log" 2>&1 &
  mp=$!
  echo "OBS LIVE SRT PREVIEW on laptop; OBS local MKV buffer recording."
  sleep 28
  echo "=== OBS ==="
  tail -26 "$BASE/logs/obs-console.log" | cut -c 1-180 || true
  echo "=== MPV ==="
  tail -16 "$BASE/logs/mpv.log" | cut -c 1-180 || true
  echo "=== BUFFER ==="
  find "$OUT" -maxdepth 1 -type f -name '*.mkv' -printf '%f (%s bytes)\n'
  [[ -n "$(find "$OUT" -maxdepth 1 -type f -name '*.mkv' -print -quit)" ]] || { echo "FAIL: no OBS A/V recording produced"; return 6; }
  echo "OBS capture finished; allowing output to finalize during cleanup."
}
case "$*" in
  audit) check ;;
  stage) stage ;;
  run) run_test ;;
  status)
    echo "OBS buffer files:"
    find "$OUT" -maxdepth 1 -type f -name '*.mkv' -printf '%p (%s bytes)\n' 2>/dev/null || true
    echo "OBS logs:"
    grep -Ei 'XSHM|pulse|recording|streaming|missed|skipped|render|encoder|error|warning' "$BASE/logs/obs-console.log" 2>/dev/null | tail -35 || true
    ;;
  *) echo "Usage: sudo bash $0 {audit|stage|run|status}"; exit 2 ;;
esac
