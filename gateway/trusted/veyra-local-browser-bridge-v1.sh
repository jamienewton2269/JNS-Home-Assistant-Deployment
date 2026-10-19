#!/usr/bin/env bash
# Veyra local-only virtual-browser preview v1; no TCP listeners.
set -Eeuo pipefail
BASE=/run/veyra-browser-bridge
SOCK=$BASE/browser.sock
case "${1:-}" in
 install)
  [ "$(id -u)" = 0 ] || { echo 'sudo required'; exit 2; }
  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends x11vnc python3-gi gir1.2-gtk-3.0 gir1.2-gtk-vnc-2.0
  install -d -m 2770 -o jnsadmin -g video "$BASE"
  cat >/usr/local/libexec/veyra-browser-viewer.py <<'PY'
#!/usr/bin/python3
import gi, os, socket, sys
gi.require_version('Gtk','3.0')
gi.require_version('GtkVnc','2.0')
from gi.repository import Gtk, GtkVnc, GLib
path=sys.argv[1]
sock=socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
sock.connect(path)
w=Gtk.Window(title='Veyra virtual browser — Escape to close')
w.set_default_size(1100,650)
d=GtkVnc.Display()
d.set_size_request(800,450)
w.add(d)
def keypress(_w,e):
    if e.keyval==65307: w.destroy(); return True
    return False
w.connect('key-press-event',keypress)
w.connect('destroy',Gtk.main_quit)
w.show_all()
if not d.open_fd(sock.detach()):
    raise SystemExit('GtkVnc open_fd failed')
# Escape is reserved to close the local preview; input forwarded in other cases.
Gtk.main()
PY
  chmod 755 /usr/local/libexec/veyra-browser-viewer.py
  echo 'BRIDGE_INSTALLED. Existing kiosk/OBS/Chrome unchanged.'
 ;;
 start)
  [ "$(id -un)" = jnsadmin ] || { echo 'Run as jnsadmin'; exit 2; }
  mkdir -p "$BASE"
  [ -S /tmp/.X11-unix/X92 ] || { echo 'Chrome virtual display :92 missing'; exit 3; }
  if [ -f "$BASE/server.pid" ] && kill -0 "$(cat "$BASE/server.pid")" 2>/dev/null; then
   echo 'Bridge already active';exit 0
  fi
  rm -f "$SOCK"
  DISPLAY=:92 x11vnc -display :92 -unixsock "$SOCK" -rfbport 0 -noxdamage -shared -forever -nopw -quiet -o /home/jnsadmin/veyra-obs-test/bridge.log &
  pid=$!
  echo "$pid" >"$BASE/server.pid"
  sleep 2
  if ! kill -0 "$pid" 2>/dev/null || [ ! -S "$SOCK" ]; then echo 'Bridge failed'; tail -n 25 /home/jnsadmin/veyra-obs-test/bridge.log;exit 4; fi
  chgrp video "$SOCK"
  chmod 660 "$SOCK"
  echo 'TCP listener check:'
  ss -H -ltnp | grep -F "pid=$pid," && { echo 'Unexpected TCP listener; stopping bridge'; kill -TERM "$pid"; exit 7; } || :
  echo 'BRIDGE_READY (Unix socket only, no TCP).'
 ;;
 preview)
  [ "$(id -u)" = 0 ] || { echo 'Run preview via sudo'; exit 2; }
  [ -S "$SOCK" ] || { echo 'Start bridge as jnsadmin first';exit 3; }
  id veyra >/dev/null
  uid=$(id -u veyra)
  runtime=/run/user/$uid
  if [ ! -d "$runtime" ]; then echo 'Kiosk user runtime missing';exit 4;fi
  wayland=$(find "$runtime" -maxdepth 1 -type s -name 'wayland-*' -printf '%f\n' | head -n1)
  [ -n "$wayland" ] || { echo 'Wayland display socket missing; no preview started';exit 5; }
  # Preview does not change systemd compositor/kiosk. Timeout bounds test to 60s.
  echo 'Starting on-screen preview for 60 seconds; Escape should dismiss it sooner.'
  runuser -u veyra -- env XDG_RUNTIME_DIR="$runtime" WAYLAND_DISPLAY="$wayland" GDK_BACKEND=wayland timeout --signal=TERM 60s /usr/bin/python3 /usr/local/libexec/veyra-browser-viewer.py "$SOCK"
 ;;
 status)
  ls -l "$SOCK" 2>/dev/null || :
  ss -H -ltnp | grep -E ':(5900|5901|5902)\b' || :
  if [ -f "$BASE/server.pid" ]; then ps -p "$(cat "$BASE/server.pid")" -o pid,args || :; fi
 ;;
 stop)
  if [ -f "$BASE/server.pid" ]; then
   pid=$(cat "$BASE/server.pid")
   if [ -r "/proc/$pid/cmdline" ] && tr '\0' ' ' <"/proc/$pid/cmdline" | grep -Fq 'x11vnc -display :92'; then kill -TERM "$pid"; fi
   rm -f "$BASE/server.pid"
  fi
  rm -f "$SOCK"
  echo 'Stopped bridge only.'
 ;;
 *) echo 'Usage: sudo bash SCRIPT install | bash SCRIPT start|status|stop | sudo bash SCRIPT preview'; exit 2;;
esac
