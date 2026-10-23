#!/usr/bin/env bash
# VEYRA v0.7.2: PASSIVE playback evidence. No system changes or media capture.
set -Eeo pipefail
MODE="$1"
[[ -n "$MODE" ]] || MODE=status
case "$MODE" in status|sample) ;; *) echo "Usage: sudo bash $0 {status|sample}" >&2; exit 2 ;; esac
(( EUID == 0 )) || { echo "Run with sudo for read-only process inspection" >&2; exit 2; }
CAP=veyra-virtual-loopback-v01.service
TV=veyra-tv-v072.service
OLD_TV=veyra-tv-v070.service
BASE=/opt/veyra/virtual-loopback-v01/shared-test-v072
EXPECTED_SEGMENTS=450
if [[ "$(systemctl is-active veyra-tv-v072.service 2>/dev/null || true)" != active ]]; then
  if [[ "$(systemctl is-active veyra-tv-v070.service 2>/dev/null || true)" == active ]]; then
    TV="$OLD_TV"
    BASE=/opt/veyra/virtual-loopback-v01/shared-test-v070
    EXPECTED_SEGMENTS=10
  fi
fi
LOG="$BASE/encoder.log"
state() { systemctl is-active "$1" 2>/dev/null || true; }
echo "=== VEYRA playback quality evidence v0.7.2 (read-only) ==="
date -Is
echo "=== Service state ==="
for unit in veyra-kiosk.service "$CAP" veyra-itvx-vnc-v01.service "$OLD_TV" veyra-tv-v072.service veyra-tv-adcover-v070.service veyra-advision-v071.service; do
  printf '%-43s %s\n' "$unit" "$(state "$unit")"
done
echo "Virtual display :92: $([[ -S /tmp/.X11-unix/X92 ]] && echo present || echo missing)"
echo "Intel render device: $([[ -c /dev/dri/renderD128 ]] && echo present || echo missing)"
if command -v loginctl >/dev/null; then
  sessions=$(loginctl list-sessions --no-legend 2>/dev/null | wc -l)
  echo "logind sessions: $sessions (look for abnormal growth)"
fi
echo "=== Original recorder: inspect only, NEVER signal ==="
cg=$(systemctl show -p ControlGroup --value "$CAP" 2>/dev/null || true)
found=0
if [[ -n "$cg" && -d "/sys/fs/cgroup$cg" ]]; then
  while read -r pid; do
    [[ "$pid" =~ ^[0-9]+$ && -r "/proc/$pid/cmdline" ]] || continue
    [[ "$(cat "/proc/$pid/comm" 2>/dev/null || true)" == ffmpeg ]] || continue
    # Check process identity privately; never print command arguments or credentials.
    args=$(tr '\0' ' ' < "/proc/$pid/cmdline")
    [[ "$args" == *x11grab* && "$args" == *:92* ]] || continue
    found=$((found+1))
    ps -o pid=,stat=,etime=,pcpu=,rss= -p "$pid" |
      awk '{printf "recorder PID=%s state=%s elapsed=%s cpu(lifetime)=%s%% rss=%sKiB\n",$1,$2,$3,$4,$5}'
    if ps -o stat= -p "$pid" | grep -Eq '^[Tt]'; then
      if [[ "$(state "$TV")" == active ]]; then
        echo "NOTE: recorder currently stopped by TV pilot; verify recovery after viewing."
      else
        echo "WARNING: recorder stopped while pilot inactive. Investigate recovery safely."
      fi
    fi
  done < <(find "/sys/fs/cgroup$cg" -name cgroup.procs -exec cat {} + 2>/dev/null | sort -un)
fi
(( found > 0 )) || echo "CHECK: no matching recorder PID observed; not proof of a fault."
(( found <= 1 )) || echo "WARNING: multiple recorder matches; verify process ownership."
echo "=== Relevant process counts ==="
for name in ffmpeg ffplay cage Xvfb chrome chromium; do
  count=$(ps -eo comm= | grep -Fxc "$name" || true)
  printf '%-10s processes=%s\n' "$name" "$count"
done
echo "=== Current encoder progress (log excerpt only) ==="
if [[ -f "$LOG" ]]; then
  tail -c 12000 "$LOG" | tr '\r' '\n' |
    grep -E '^[[:space:]]*frame=|^[[:space:]]*bench:' | tail -n 5 | cut -c 1-220 || true
else
  echo "No v0.7.0 encoder log found."
fi
echo "=== Ring segment metadata ONLY; no video read ==="
python3 - "$BASE/segments" "$EXPECTED_SEGMENTS" <<'PY'
import glob,os,sys,time
files=glob.glob(os.path.join(sys.argv[1],"segment[0-9]*.ts"))
stats=[]
for f in files:
    try: stats.append(os.stat(f))
    except OSError: pass
age=(f"{time.time()-max(s.st_mtime for s in stats):.1f}s" if stats else "n/a")
expect=int(sys.argv[2])
print(f"segment files={len(stats)}/{expect}; total size={sum(s.st_size for s in stats)} bytes; newest age={age}")
print(f"Pilot ring target: {expect} x 4-second segments, approximately {expect*4/60:.2f} minutes.")
print("Ring retention does not yet imply pause/rewind/seek controls.")
PY
if [[ "$MODE" == sample ]]; then
  echo "=== Eight-second passive process CPU observation ==="
  python3 - <<'PY'
import glob,os,time
names={"chrome","chromium","ffmpeg","ffplay","Xvfb","cage"}
hz=os.sysconf("SC_CLK_TCK")
def read():
    result={}
    for p in glob.glob("/proc/[0-9]*"):
        try:
            name=open(p+"/comm",encoding="ascii").read().strip()
            if name not in names: continue
            s=open(p+"/stat",encoding="ascii").read()
            data=s[s.rfind(")")+2:].split()
            ticks=int(data[11])+int(data[12])
            rss=int(data[21])*os.sysconf("SC_PAGE_SIZE")
            result[int(p.rsplit("/",1)[1])]=(name,ticks,rss)
        except (OSError,ValueError,IndexError): pass
    return result
start=read(); begin=time.monotonic()
time.sleep(8)
end=read(); elapsed=time.monotonic()-begin
for name in sorted(names):
    ticks=sum(max(0,new[1]-old[1]) for pid,old in start.items()
              if old[0]==name and pid in end for new in [end[pid]] if new[0]==name)
    mem=sum(v[2] for v in end.values() if v[0]==name)/1024**2
    count=sum(v[0]==name for v in end.values())
    print(f"{name:<10} CPU={ticks/hz/elapsed*100:6.1f}% of one core; RSS sum={mem:7.0f}MiB; processes={count}")
print("CPU observations cover all local processes with these names, not exclusively ITVX.")
print("These are not GPU utilisation or source-unique-frame measurements.")
PY
fi
echo "END: no service, capture, login, profile, audio route or config changed."
