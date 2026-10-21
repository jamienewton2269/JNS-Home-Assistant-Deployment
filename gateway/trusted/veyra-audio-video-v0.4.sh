#!/usr/bin/env bash
set -Eeuo pipefail
R=/opt/veyra/virtual-loopback-v01
SINK=veyra_virtual_capture
BACK="$R/runner.sh.pre-audio-v04"
OUT="$R/processed-v04"
ID=$(id -u veyra)
PULSE="unix:/run/user/$ID/pulse/native"
pa(){ runuser -u veyra -- env XDG_RUNTIME_DIR="/run/user/$ID" PULSE_SERVER="$PULSE" pactl "$@"; }
sink(){
  pa list short sinks | awk '{print $2}' | grep -Fxq "$SINK" && return 0
  pa load-module module-null-sink "sink_name=$SINK" 'sink_properties=device.description=Veyra_Virtual_Chrome' >/dev/null
  pa list short sinks | awk '{print $2}' | grep -Fxq "$SINK"
}
route(){
  local sid pid n=0
  while read -r sid pid; do
    [[ "$sid" =~ ^[0-9]+$ && "$pid" =~ ^[0-9]+$ && -r "/proc/$pid/environ" ]] || continue
    if tr '\0' '\n' <"/proc/$pid/environ" | grep -Fxq 'DISPLAY=:92'; then
      pa move-sink-input "$sid" "$SINK"
      pa set-sink-input-mute "$sid" 0
      n=$((n+1))
    fi
  done < <(pa list sink-inputs | awk '/^Sink Input #[0-9]+/ {id=$3;gsub("#","",id)} /application.process.id =/ {pid=$3;gsub(/"/,"",pid);if(id!="") print id,pid}')
  echo "Virtual Chrome sink inputs routed: $n"
}
install_audio(){
  [[ -f "$R/runner.sh" ]] || { echo 'Missing virtual loopback runner';exit 2; }
  sink
  [[ -e "$BACK" ]] || cp -p "$R/runner.sh" "$BACK"
  python3 - "$R/runner.sh" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1]); s=p.read_text()
tag='export PULSE_SINK=veyra_virtual_capture'
if tag not in s:
    k='export DISPLAY=:92'
    if s.count(k)!=1: raise SystemExit('Runner format unexpected; no patch')
    p.write_text(s.replace(k,k+'\n'+tag,1))
print('Future virtual Chrome audio now routed to virtual sink')
PY
  bash -n "$R/runner.sh"
  route
  echo 'Physical kiosk unchanged; capture service not restarted'
}
process(){
  mkdir -p "$OUT"
  python3 - "$R/buffer" "$OUT" <<'PY'
from pathlib import Path
import subprocess,sys,os
buf,out=map(Path,sys.argv[1:])
files=sorted(buf.glob('segment*.ts'),key=lambda p:p.stat().st_mtime,reverse=True)
src=None
for f in files[2:]:
    if f.stat().st_size<100000:continue
    try:
        p=subprocess.run(['ffmpeg','-nostdin','-v','error','-xerror','-i',str(f),'-map','0:v:0','-f','null','-'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=18)
        if p.returncode==0:src=f;break
    except subprocess.TimeoutExpired:pass
if src is None:raise SystemExit('No valid completed segment; old output not modified')
print('Source:',src,flush=True)
tmp=out/'processed.new.ts';dst=out/'processed.ts'
try:
    subprocess.run(['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y','-i',str(src),'-f','lavfi','-i','testsrc2=size=320x180:rate=24','-filter_complex','[1:v]format=yuv420p[c];[0:v][c]overlay=W-w-24:24:shortest=1[v]','-map','[v]','-an','-t','4','-threads','2','-c:v','mpeg2video','-q:v','6','-g','24','-bf','0','-f','mpegts',str(tmp)],check=True,timeout=90)
    test=subprocess.run(['ffmpeg','-nostdin','-v','error','-xerror','-i',str(tmp),'-map','0:v:0','-f','null','-'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=20)
    if test.returncode!=0 or tmp.stat().st_size<100000:raise RuntimeError('Processed video invalid')
    os.replace(tmp,dst)
    subprocess.run(['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y','-i',str(dst),'-frames:v','1',str(out/'proof.png')],check=True,timeout=20)
    print('PASS:',dst)
except Exception:
    tmp.unlink(missing_ok=True)
    raise
PY
}
if [[ "$EUID" -ne 0 ]];then echo 'Run with sudo';exit 2;fi
case "$(printf '%s' "$@")" in
 preflight) [[ -f "$R/runner.sh" ]] && pa info >/dev/null && command -v ffmpeg && command -v ffprobe && echo 'PASS';;
 install) install_audio;;
 route) sink;route;;
 audio-test)
  sink;mkdir -p "$OUT"
  runuser -u veyra -- env XDG_RUNTIME_DIR="/run/user/$ID" PULSE_SERVER="$PULSE" ffmpeg -hide_banner -nostdin -loglevel error -y -f pulse -i "$SINK.monitor" -t 12 -c:a pcm_s16le "$OUT/virtual-audio.wav"
  ffprobe -v error -show_entries format=duration,size -of default=nw=1 "$OUT/virtual-audio.wav";;
 process) process;;
 status) pa list short sinks | grep -F "$SINK" || true;pa list short sink-inputs;;
 rollback) [[ -f "$BACK" ]] || { echo 'Backup absent';exit 2;};cp -p "$BACK" "$R/runner.sh";bash -n "$R/runner.sh";echo 'Runner restored; no service restarted';;
 *) echo "Usage: sudo bash $0 {preflight|install|route|audio-test|process|status|rollback}";exit 2;;
esac
