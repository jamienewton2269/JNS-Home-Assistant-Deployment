#!/usr/bin/env bash
# VEYRA OBS GPU Wayland trial v1.3 — bounded, RECORD-ONLY experiment.
# Never restarts Chrome, Cage, VNC or the original legacy recorder.
set -Eeuo pipefail
ROOT=/opt/veyra/obs-backend-v1/av-qa-v13
WS=/usr/local/libexec/veyra-obs-ws-control-v1.2.py
RUN=''
OBS_GROUP=''
X_GROUP=''
STOPPED=0
say() { printf '%s\n' "$*"; }
block() { say "SAFETY STOP: $*" >&2; return 2; }
pulse_env() {
  local r
  r="/run/user/$(id -u veyra)"
  runuser -u veyra -- env XDG_RUNTIME_DIR="$r" PULSE_SERVER="unix:$r/pulse/native" "$@"
}
audit() {
  [[ $EUID == 0 ]] || { block "sudo required"; return 2; }
  for c in obs cage ffprobe mpv python3 xdpyinfo pactl strings flock runuser setsid timeout; do
    command -v "$c" >/dev/null || { block "missing $c"; return 2; }
  done
  [[ -r "$WS" ]] || { block "install websocket helper at $WS first"; return 2; }
  [[ -f /usr/lib/x86_64-linux-gnu/obs-plugins/linux-capture.so ]] ||
    { block "linux-capture plugin missing"; return 2; }
  strings /usr/lib/x86_64-linux-gnu/obs-plugins/linux-capture.so |
    grep -Fx xshm_input >/dev/null || { block "plugin lacks xshm_input"; return 2; }
  for svc in veyra-kiosk.service veyra-itvx-vnc-v01.service veyra-virtual-loopback-v01.service; do
    systemctl is-active --quiet "$svc" || { block "protected service $svc inactive"; return 2; }
  done
  [[ -S /tmp/.X11-unix/X92 ]] || { block "ITVX X display :92 unavailable"; return 2; }
  [[ -c /dev/dri/renderD128 ]] || { block "Intel render node missing"; return 2; }
  local runtime
  runtime="/run/user/$(id -u veyra)"
  [[ -d "$runtime" ]] || { block "veyra user runtime missing"; return 2; }
  # Preflight only. This must be Qt Wayland, not software-rendered Xvfb.
  local qt_plugin=''
  for root in /usr/lib/x86_64-linux-gnu/qt6/plugins/platforms /usr/lib/qt6/plugins/platforms /usr/lib/x86_64-linux-gnu/qt5/plugins/platforms; do
    [[ -e "$root/libqwayland-generic.so" || -e "$root/libqwayland-egl.so" ]] && qt_plugin=present
  done
  [[ "$qt_plugin" == present ]] || { block "Qt Wayland platform plugin missing; no package installed"; return 2; }
  [[ ! -e /run/veyra-obs-av-v11.recovery ]] ||
    { block "unresolved v1.1 recorder recovery marker"; return 2; }
  for svc in veyra-tv-v079.service veyra-tv-v080.service; do
    ! systemctl is-active --quiet "$svc" ||
      { block "overlapping display trial: $svc"; return 2; }
  done
  runuser -u veyra -- env DISPLAY=:92 xdpyinfo >/dev/null ||
    { block "veyra cannot read X display :92"; return 2; }
  pulse_env pactl list short sources | grep -Fq veyra_virtual_capture.monitor ||
    { block "existing ITVX PulseAudio monitor missing"; return 2; }
  python3 - <<'PY'
import socket
s=socket.socket()
try: s.bind(("127.0.0.1",24593))
except OSError: raise SystemExit("SAFETY STOP: OBS v1.2 control port already occupied")
finally: s.close()
PY
  say "PASS: protected services healthy; corrected XSHM plugin present."
}
stage() {
  audit
  install -d -m 700 -o veyra -g veyra "$ROOT" "$ROOT/runs"
  RUN="$ROOT/runs/$(date -u +%Y%m%dT%H%M%SZ)-$$"
  [[ ! -e "$RUN" ]] || { block "run directory already exists"; return 2; }
  install -d -m 700 -o veyra -g veyra "$RUN" "$RUN/config" "$RUN/buffer" "$RUN/logs"
  python3 - "$RUN" <<'PY'
import pathlib,json,uuid,secrets,sys
run=pathlib.Path(sys.argv[1]); root=run/'config/obs-studio'
scenes=root/'basic/scenes'; profile=root/'basic/profiles/VEYRA_QA_V13'
web=root/'plugin_config/obs-websocket'
for folder in (scenes,profile,web): folder.mkdir(parents=True,exist_ok=True)
new=lambda:str(uuid.uuid4())
s,v,a=new(),new(),new()
video={"name":"ITVX XSHM :92","uuid":v,"id":"xshm_input","versioned_id":"xshm_input",
       "settings":{"advanced":True,"server":":92","screen":0,"show_cursor":False},"mixers":0}
audio={"name":"ITVX monitor audio","uuid":a,"id":"pulse_output_capture",
       "versioned_id":"pulse_output_capture",
       "settings":{"device_id":"veyra_virtual_capture.monitor"},"mixers":1}
def item(source,num):
 return {"name":source["name"],"source_uuid":source["uuid"],"id":num,
         "visible":True,"locked":True,"pos":{"x":0,"y":0},
         "scale":{"x":1,"y":1},"rot":0,"align":5,"bounds_type":0}
scene={"name":"ITVX Quality","uuid":s,"id":"scene","versioned_id":"scene",
       "settings":{"items":[item(video,1),item(audio,2)],"id_counter":3}}
collection={"name":"VEYRA_QA_V13","current_scene":"ITVX Quality",
 "current_program_scene":"ITVX Quality","scene_order":[{"name":"ITVX Quality"}],
 "sources":[scene,video,audio],"groups":[],"transitions":[],"quick_transitions":[],
 "current_transition":"Cut","transition_duration":0,"resolution":{"x":1366,"y":768},"version":2}
assert all(x["source_uuid"] in {s,v,a} and x["visible"] for x in scene["settings"]["items"])
assert video["id"]=="xshm_input" and video["settings"]["server"]==":92"
(scenes/'VEYRA_QA_V13.json').write_text(json.dumps(collection,indent=2))
(root/'user.ini').write_text(
 "[General]\nFirstRun=true\nConfirmOnExit=false\n"
 "[Basic]\nProfile=VEYRA_QA_V13\nProfileDir=VEYRA_QA_V13\n"
 "SceneCollection=VEYRA_QA_V13\nSceneCollectionFile=VEYRA_QA_V13\n"
 "[BasicWindow]\nPreviewEnabled=false\n")
(profile/'basic.ini').write_text(
 "[General]\nName=VEYRA_QA_V13\n"
 "[Video]\nBaseCX=1366\nBaseCY=768\nOutputCX=1364\nOutputCY=768\n"
 "FPSType=1\nFPSInt=25\nScaleType=bicubic\nColorFormat=NV12\n"
 "ColorSpace=709\nColorRange=Partial\n"
 "[Audio]\nSampleRate=48000\nChannelSetup=Stereo\n"
 "[Output]\nMode=Simple\n"
 "[SimpleOutput]\nFilePath="+str(run/'buffer')+"\nRecFormat2=mkv\n"
 "RecQuality=Stream\nStreamEncoder=x264\nRecEncoder=x264\n"
 "VBitrate=6500\nABitrate=160\nPreset=ultrafast\n"
 "UseAdvanced=true\nx264Settings=keyint=50\n")
(web/'config.json').write_text(json.dumps({
 "first_load":False,"server_enabled":True,"server_port":24593,
 "alerts_enabled":False,"auth_required":True,
 "server_password":secrets.token_urlsafe(32)},indent=2))
assert not (profile/'service.json').exists()  # SRT completely disabled
PY
  chown -R veyra:veyra "$RUN"
  chmod 600 "$RUN/config/obs-studio/plugin_config/obs-websocket/config.json"
  say "STAGED=$RUN"
  say "XSHM=xshm_input SERVER=:92 OBS_UI=PRIVATE_HEADLESS_WAYLAND NO_SRT=true"
}
control() {
  python3 "$WS" "$1" --config \
    "$RUN/config/obs-studio/plugin_config/obs-websocket/config.json"
}
cleanup() {
  local rc=$?
  trap - EXIT INT TERM
  set +e
  if [[ -n "$OBS_GROUP" ]]; then
    if [[ "$STOPPED" -ne 1 ]]; then
      control stop && STOPPED=1
    fi
    [[ "$STOPPED" -eq 1 ]] || say "WARNING: recording finalisation unverified."
    kill -TERM -- "-$OBS_GROUP" 2>/dev/null || true
    sleep 2
    kill -KILL -- "-$OBS_GROUP" 2>/dev/null || true
    wait "$OBS_GROUP" 2>/dev/null || true
  fi
  if [[ -n "$X_GROUP" ]]; then
    # X_GROUP is unused: OBS and its disposable Cage compositor share OBS_GROUP.
    echo "WARN: unexpected second graphics group; left untouched."
  fi
  say "CLEANUP: existing ITVX/Chrome, kiosk, VNC, recorder never stopped."
  exit "$rc"
}
frames() {
  local f="$1" d t rc
  d=$(mktemp -d "$RUN/frames-XXXXXXXX")
  chown veyra:veyra "$d"
  for t in 3 8 13; do
    install -d -m 700 -o veyra -g veyra "$d/$t"
    rc=0
    timeout -k 2s 12s runuser -u veyra -- \
      mpv --no-config --no-audio --no-sub --hwdec=no \
      --start="$t" --frames=1 --vo=image --vo-image-format=png \
      --vo-image-outdir="$d/$t" "$f" >"$RUN/logs/frame-$t.log" 2>&1 || rc=$?
    say "FRAME_EXTRACT_SECOND=$t EXIT=$rc"
  done
  local result=0
  python3 - "$d" <<'PY' || result=$?
from pathlib import Path
import sys,hashlib
d=Path(sys.argv[1]); hashes=[]
for sec in (3,8,13):
 files=list((d/str(sec)).glob("*.png"))
 if len(files)!=1:
  print(f"FAIL: frame {sec} unavailable"); raise SystemExit(4)
 raw=files[0].read_bytes(); h=hashlib.sha256(raw).hexdigest()
 print(f"FRAME_SECOND={sec} PNG_BYTES={len(raw)} SHA256_PREFIX={h[:12]}")
 hashes.append(h)
if len(set(hashes))<2:
 print("FAIL: all sampled frames identical; moving picture not demonstrated")
 raise SystemExit(5)
print("PASS: differing decoded frames; programme/video content still requires visual acceptance")
PY
  rm -rf -- "$d"
  return "$result"
}
run_test() {
  exec 9>/run/lock/veyra-obs-v12.lock
  flock -n 9 || { block "another OBS v1.2 trial running"; return 2; }
  stage
  trap cleanup EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  # Isolated Cage backend is explicitly headless; no DRM modeset or physical window.
  # OBS uses Wayland for GL, while its XSHM source connects separately to :92.
  # No provider profile, VNC or existing virtual recorder is changed.
  local private_runtime="$RUN/runtime"
  install -d -m 700 -o veyra -g veyra "$private_runtime"
  setsid runuser -u veyra -- env \
    -u DISPLAY -u WAYLAND_DISPLAY -u WAYLAND_SOCKET -u _WAYLAND_DISPLAY \
    XDG_RUNTIME_DIR="$private_runtime" \
    WLR_BACKENDS=headless WLR_HEADLESS_OUTPUTS=1 WLR_LIBINPUT_NO_DEVICES=1 \
    WLR_RENDERER=gles2 WLR_RENDER_DRM_DEVICE=/dev/dri/renderD128 \
    LIBGL_ALWAYS_SOFTWARE=0 \
    cage -- env DISPLAY=:92 QT_QPA_PLATFORM=wayland \
      XDG_CONFIG_HOME="$RUN/config" \
      PULSE_SERVER="unix:/run/user/$(id -u veyra)/pulse/native" \
      obs --multi --only-bundled-plugins --disable-updater \
        --disable-shutdown-check --disable-missing-files-check \
        --profile VEYRA_QA_V13 --collection VEYRA_QA_V13 \
        --scene "ITVX Quality" --startrecording \
    >"$RUN/logs/obs-console.log" 2>&1 &
  OBS_GROUP=$!
  local n verified=0 log clip err
  log="$RUN/logs/obs-console.log"
  for n in 1 2 3 4 5 6 7 8 9 10 11 12; do
    sleep 1
    kill -0 "$OBS_GROUP" 2>/dev/null ||
      { block "OBS exited during startup"; tail -25 "$log"; return 4; }
    if grep -Eiq "llvmpipe|softpipe|Software Rasterizer" "$log"; then
      block "GPU REQUIREMENT FAILED: OBS or Cage is software-rendered"; tail -35 "$log"; return 4
    fi
    if grep -Eiq "Source ID .* not found|Failed to create source|Unable to open X display|Missing SHM extension|failed to attach shm" "$log"; then
      block "OBS XSHM source failed"; tail -30 "$log"; return 4
    fi
    if control verify >"$RUN/logs/verify.log" 2>&1; then verified=1; break; fi
  done
  [[ "$verified" -eq 1 ]] ||
    { block "OBS source or recording not verified"; tail -15 "$RUN/logs/verify.log"; tail -25 "$log"; return 5; }
  cat "$RUN/logs/verify.log"
  if ! grep -Eiq "Loading up OpenGL on adapter.*(Intel|Mesa DRI Intel|UHD Graphics|HD Graphics)" "$log"; then
    block "GPU ADAPTER NOT VERIFIED: refusing the recording as a GPU result"
    grep -Ei "OpenGL|renderer|EGL|drm|failed|error" "$log" | tail -40 || true
    return 5
  fi
  say "OBS_INTEL_GPU_ADAPTER_VERIFIED"
  say "CAPTURE: 18-second isolated GPU-Wayland OBS-only recording; SRT disabled."
  sleep 18
  control stop | tee "$RUN/logs/stop.log"
  STOPPED=1
  sleep 2
  if grep -Eiq "Source ID .* not found|Failed to create source|Unable to open X display|Missing SHM extension|failed to attach shm" "$log"; then
    block "OBS logged an XSHM error"; return 6
  fi
  [[ "$(find "$RUN/buffer" -maxdepth 1 -type f -name '*.mkv' | wc -l)" -eq 1 ]] ||
    { block "expected one fresh OBS MKV"; return 6; }
  clip=$(find "$RUN/buffer" -maxdepth 1 -type f -name '*.mkv' -print -quit)
  err="$RUN/logs/ffprobe.stderr"
  ffprobe -hide_banner -v warning \
    -show_entries 'format=duration,size:stream=index,codec_type,codec_name,width,height,avg_frame_rate,sample_rate,channels' \
    -of json "$clip" 2>"$err" ||
    { block "ffprobe failed"; cat "$err"; return 7; }
  if grep -Eiq 'File ended prematurely|Invalid data|truncated|error' "$err"; then
    block "MKV appears unfinalised"; cat "$err"; return 7
  fi
  ffprobe -v error -show_entries stream=codec_type -of csv=p=0 "$clip" |
    grep -Fxq video || { block "no video stream"; return 7; }
  ffprobe -v error -show_entries stream=codec_type -of csv=p=0 "$clip" |
    grep -Fxq audio || { block "no audio stream"; return 7; }
  frames "$clip" || return 8
  echo "=== OBS RENDERING PERFORMANCE ==="
  python3 - "$log" <<'PY'
import pathlib,re,sys
s=pathlib.Path(sys.argv[1]).read_text(errors="replace")
m=re.findall(r'Number of lagged frames due to rendering lag/stalls:\s*(\d+)\s*\(([\d.]+)%\)',s)
if not m:
    print("WARN: OBS rendering statistics missing; require visual quality validation")
    raise SystemExit(9)
count,percent=m[-1]
print(f"OBS_RENDER_LAG_FRAMES={count} OBS_RENDER_LAG_PERCENT={percent}")
if float(percent)>5:
    print("FAIL: more than 5% OBS rendering lag; video remains unacceptable")
    raise SystemExit(10)
print("PASS: OBS rendering stalls <=5%; still require motion, sound and sync acceptance")
PY
  say "CANDIDATE_MKV=$clip"
  say "GPU_CAPTURE_CANDIDATE only; original recorder still active during test."
  say "REPLAY: sudo bash veyra-obs-live-av-quality-v1.2.sh play '$clip'"
}
play_saved() {
  local clip="$1" rt sock sink
  [[ $EUID == 0 ]] || { block "sudo required"; return 2; }
  clip=$(readlink -f -- "$clip") || return 2
  case "$clip" in
    "$ROOT"/runs/*/buffer/*.mkv) ;;
    *) block "replay accepts only v1.2 recorded MKVs"; return 2 ;;
  esac
  [[ -s "$clip" ]] || { block "clip empty or missing"; return 2; }
  systemctl is-active --quiet veyra-kiosk.service ||
    { block "kiosk inactive"; return 2; }
  rt="/run/user/$(id -u veyra)"
  sock=$(find "$rt" -maxdepth 1 -type s -name 'wayland-*' -printf '%f\n' | sort | head -1)
  [[ -n "$sock" ]] || { block "Cage Wayland socket unavailable"; return 2; }
  sink=$(pulse_env pactl list short sinks | awk '$2~/^alsa_output/{print $2;exit}')
  [[ -n "$sink" ]] || { block "physical speaker sink missing"; return 2; }
  runuser -u veyra -- env XDG_RUNTIME_DIR="$rt" WAYLAND_DISPLAY="$sock" \
    PULSE_SERVER="unix:$rt/pulse/native" PULSE_SINK="$sink" \
    timeout -k 2s 45s mpv --no-config --fullscreen --no-border \
      --vo=gpu --gpu-context=wayland --hwdec=no --ao=pulse "$clip"
}
case "$1" in
  audit) audit ;;
  stage) stage ;;
  run) run_test ;;
  status) find "$ROOT/runs" -path '*/buffer/*.mkv' -type f -printf '%p %s bytes\n' 2>/dev/null || true ;;
  play) [[ $# -eq 2 ]] || { block "play requires the MKV path"; exit 2; }; play_saved "$2" ;;
  *) say "Usage: sudo bash $0 {audit|stage|run|status|play /path/to/clip.mkv}"; exit 2 ;;
esac
