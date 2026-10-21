#!/usr/bin/env bash
# Veyra recorder load A/B diagnostic v0.5.5.
# Pauses ONLY virtual-display recorder FFmpeg, never Chrome or Xvfb.
# Always resumes it; a separate systemd timer is an emergency failsafe.
set -Eeuo pipefail
if (( EUID != 0 )); then echo "Use sudo"; exit 2; fi
CAP=veyra-virtual-loopback-v01.service
VNC=veyra-itvx-vnc-v01.service
PROBE=/home/jnsadmin/veyra-motion-probe-v0.5.4.sh
[[ -s "$PROBE" ]] || { echo "The v0.5.4 probe is missing"; exit 2; }
bash -n "$PROBE"
for name in "$CAP" "$VNC" veyra-kiosk.service; do
  systemctl is-active --quiet "$name" || { echo "SAFETY STOP: $name not active"; exit 2; }
done
for name in veyra-live-av-v052.service veyra-live-av-v051.service; do
  if systemctl is-active --quiet "$name"; then
    echo "SAFETY STOP: player $name still running"
    exit 2
  fi
done
cg=$(systemctl show -p ControlGroup --value "$CAP")
if [[ -z "$cg" || ! -d "/sys/fs/cgroup$cg" ]]; then
  echo "SAFETY STOP: recorder cgroup unavailable"
  exit 2
fi
mapfile -t recorders < <(
  find "/sys/fs/cgroup$cg" -name cgroup.procs -exec cat {} + |
  sort -un |
  while read -r pid; do
    [[ -r "/proc/$pid/comm" ]] || continue
    read -r exe < "/proc/$pid/comm" || true
    [[ "$exe" == ffmpeg ]] && echo "$pid"
  done
)
if (( ${#recorders[@]} != 1 )); then
  echo "SAFETY STOP: exactly one FFmpeg expected, found ${#recorders[@]}"
  printf 'Candidates: %s\n' "${recorders[*]}"
  exit 3
fi
pid=${recorders[0]}
cmdline=$(tr '\0' ' ' < "/proc/$pid/cmdline")
if [[ "$cmdline" != *x11grab* || "$cmdline" != *:92* ]]; then
  echo "SAFETY STOP: FFmpeg PID $pid is not the virtual-display recorder."
  echo "$cmdline"
  exit 3
fi
echo "Recorder FFmpeg: PID $pid"
echo "The rolling recorder will pause for approximately 17 seconds; browser and VNC remain active."
dir=$(mktemp -d /tmp/veyra-ab-v055.XXXXXX)
paused=0
timer=
restore() {
  if (( paused )); then
    kill -CONT "$pid" 2>/dev/null || true
    paused=0
    echo "PASS: recorder resumed ($pid)"
  fi
  if [[ -n "$timer" ]]; then
    systemctl stop "$timer.timer" >/dev/null 2>&1 || true
  fi
  rm -rf -- "$dir"
}
trap restore EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
echo
echo "=== A: NORMAL RECORDER LOAD ==="
bash "$PROBE" > "$dir/normal.log" 2>&1 || { cat "$dir/normal.log"; exit 4; }
echo
echo "=== B: ROLLING RECORDER TEMPORARILY PAUSED ==="
timer="veyra-recorder-resume-v055-$(date +%s)"
systemd-run --quiet --collect --unit="$timer" --on-active=35s /usr/bin/kill -CONT "$pid"
kill -STOP "$pid"
paused=1
bash "$PROBE" > "$dir/paused.log" 2>&1 || { cat "$dir/paused.log"; exit 5; }
kill -CONT "$pid"
paused=0
systemctl stop "$timer.timer" >/dev/null 2>&1 || true
timer=
echo "Recorder resumed. Comparing results:"
for phase in normal paused; do
  echo
  echo "=== $phase ==="
  grep -E 'ffmpeg[[:space:]]|chrome[[:space:]]|changed frames:|common intervals \(ms\)|changes each second:|median [0-9]|longest [0-9]|CAUTION|Wall time' "$dir/$phase.log" | tail -24 || true
done
echo
echo "=== FINAL SERVICE STATES ==="
for name in "$CAP" "$VNC" veyra-kiosk.service; do
  echo "$name: $(systemctl is-active "$name" 2>/dev/null || true)"
done
echo "Done. No video or audio files created."
