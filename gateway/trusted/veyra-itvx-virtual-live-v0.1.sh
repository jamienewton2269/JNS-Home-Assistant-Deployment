#!/usr/bin/env bash
set -Eeuo pipefail
ROOT=/opt/veyra/virtual-loopback-v01
RUNNER="$ROOT/runner.sh"
BACKUP="$ROOT/runner.sh.pre-itvx-live-github-v01"
CAP=veyra-virtual-loopback-v01.service
VIEW=veyra-itvx-vnc-v01.service
cmd="${1:-help}"
[[ $EUID -eq 0 ]] || { echo "Use sudo"; exit 2; }
case "$cmd" in
  install)
    [[ -f "$RUNNER" ]] || { echo "Missing working loopback runner"; exit 2; }
    command -v x11vnc >/dev/null || { echo "Install x11vnc first: sudo apt-get install -y x11vnc"; exit 2; }
    python3 - "$RUNNER" "$BACKUP" <<'PY'
from pathlib import Path
import sys
p,b=map(Path,sys.argv[1:])
s=p.read_text()
a='"file://$ROOT/test.html"'
z='"https://www.itv.com/watch"'
if a not in s and z not in s:
    raise SystemExit("Unexpected Chrome target; no change")
if a in s:
    if not b.exists(): b.write_text(s)
    p.write_text(s.replace(a,z))
print("ITVX virtual Chrome target installed; live kiosk unchanged.")
PY
    bash -n "$RUNNER"
    ;;
  start)
    [[ -f "$BACKUP" ]] || { echo "Run install first"; exit 2; }
    systemctl stop "$VIEW" 2>/dev/null || true
    systemctl stop "$CAP" 2>/dev/null || true
    systemctl reset-failed "$CAP" >/dev/null 2>&1 || true
    systemd-run --quiet --unit=veyra-virtual-loopback-v01 --collect -p User=veyra -p Group=veyra -p WorkingDirectory="$ROOT" -p KillMode=control-group -- "$RUNNER"
    sleep 4
    [[ -S /tmp/.X11-unix/X92 ]] || { echo "Virtual display not ready"; exit 2; }
    systemctl reset-failed "$VIEW" >/dev/null 2>&1 || true
    systemd-run --quiet --unit=veyra-itvx-vnc-v01 --collect -p User=veyra -p Group=veyra -p KillMode=control-group -- /usr/bin/x11vnc -display :92 -localhost -rfbport 5902 -forever -shared -nopw -noxdamage -quiet
    echo "ITVX virtual Chrome running. SSH tunnel: ssh -N -L 5902:127.0.0.1:5902 jnsadmin@veyra"
    echo "Connect VNC viewer to 127.0.0.1:5902, log in and start a programme."
    ;;
  status)
    echo "Capture: $(systemctl is-active "$CAP" 2>/dev/null || true)"
    echo "VNC: $(systemctl is-active "$VIEW" 2>/dev/null || true)"
    echo "Physical kiosk: $(systemctl is-active veyra-kiosk.service 2>/dev/null || true)"
    find "$ROOT/buffer" -maxdepth 1 -name 'segment*.ts' -size +100k -printf '%f %s bytes\n' | sort | head
    ;;
  probe)
    f=$(find "$ROOT/buffer" -maxdepth 1 -name 'segment*.ts' -size +100k -printf '%T@ %p\n' | sort -nr | sed -n '2s/^[^ ]* //p')
    [[ -n "$f" ]] || { echo "No complete segment yet"; exit 2; }
    ffprobe -v error -select_streams v:0 -show_entries stream=codec_name,width,height,r_frame_rate -of default=nw=1 "$f"
    ffmpeg -hide_banner -loglevel error -y -i "$f" -frames:v 1 "$ROOT/buffer/itvx-proof.png"
    echo "Proof: $ROOT/buffer/itvx-proof.png"
    ;;
  stop-view)
    systemctl stop "$VIEW" 2>/dev/null || true
    ;;
  rollback)
    systemctl stop "$VIEW" 2>/dev/null || true
    systemctl stop "$CAP" 2>/dev/null || true
    [[ -f "$BACKUP" ]] || { echo "Backup missing; runner unchanged"; exit 2; }
    cp "$BACKUP" "$RUNNER"
    bash -n "$RUNNER"
    echo "Original capture runner restored. Live Cage untouched."
    ;;
  *) echo "Usage: sudo bash $0 {install|start|status|probe|stop-view|rollback}"; exit 2 ;;
esac
