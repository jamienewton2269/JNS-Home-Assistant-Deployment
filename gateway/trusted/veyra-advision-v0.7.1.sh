#!/usr/bin/env bash
# VEYRA v0.7.1 — train actual provider bumper images, then use visual entry/exit to cover adverts.
# Never restart existing ITVX virtual Chrome, VNC, physical Cage, watchlist or media recorder.
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || { echo "Run using sudo";exit 2; }
ACTION="${1:-preflight}"
BASE=https://raw.githubusercontent.com/jamienewton2269/JNS-Home-Assistant-Deployment/main/gateway/trusted
ROOT=/opt/veyra/advision-v071
DB=/var/lib/veyra/advision-v071
VISION=veyra-advision-v071.service
COVER=veyra-tv-adcover-v070.service
VISION_UNIT=/etc/systemd/system/$VISION
COVER_UNIT=/etc/systemd/system/$COVER
CHECK=127.0.0.1
preflight(){
 for unit in veyra-kiosk.service veyra-virtual-loopback-v01.service veyra-itvx-vnc-v01.service;do
   systemctl is-active --quiet "$unit" || { echo "SAFETY STOP: $unit not active";return 2; }
 done
 for tool in curl python3 ffmpeg systemctl runuser pactl ffplay;do command -v "$tool" >/dev/null || { echo "Missing $tool";return 2; };done
 [[ -S /tmp/.X11-unix/X92 ]] || { echo 'Virtual ITVX display :92 is unavailable';return 2; }
 if [[ -f "$VISION_UNIT" ]] && ! grep -Fq "/opt/veyra/advision-v071/current/vision.py" "$VISION_UNIT";then
   echo "SAFETY STOP: $VISION_UNIT belongs to an unknown application";return 2
 fi
 if [[ -f "$COVER_UNIT" ]] && ! grep -Eq '/opt/veyra/(tv-night/current/cover.py|advision-v071/current/cover.py)' "$COVER_UNIT";then
   echo "SAFETY STOP: unknown advert-cover service";return 2
 fi
 if ! [[ -f "$VISION_UNIT" ]] && ss -ltnH '( sport = :8774 )' | grep -q .;then
   echo 'SAFETY STOP: port 8774 already in use';return 2
 fi
 if ! [[ -f "$COVER_UNIT" ]] && ss -ltnH '( sport = :8773 )' | grep -q .;then
   echo 'SAFETY STOP: port 8773 already in use';return 2
 fi
 echo 'PASS: Existing Veyra playback services intact, separate visual observer ports available.'
}
download(){
 curl -fLsS --retry 2 --connect-timeout 10 --max-time 35 "$1" -o "$2"
 test -s "$2"
}
install_app(){
 preflight
 local stage stamp release active
 # Never replace an active manual cover, because it could expose ITVX adverts.
 if systemctl is-active --quiet "$COVER";then
   active=$(curl -fsS --max-time 3 http://127.0.0.1:8773/api/status || true)
   if [[ "$active" == *'"active": true'* || "$active" == *'"active":true'* ]];then
      echo 'SAFETY STOP: close the active manual advert cover before upgrading it.';return 2
   fi
 fi
 install -d -m 755 -o root -g root "$ROOT"
 install -d -m 700 -o veyra -g veyra "$DB"
 stage=$(mktemp -d "$ROOT/.stage.XXXXXXXX")
 trap 'rm -rf -- "$stage"' EXIT
 echo 'Downloading provider visual recogniser and no-timer cover.'
 for file in vision.py index.html style.css app.js;do
   download "$BASE/veyra-advision-v071/$file" "$stage/$file"
 done
 for file in cover.py index.html app.js styles.css;do
   download "$BASE/veyra-tv-adcover-v071/$file" "$stage/cover-$file"
 done
 # The controller assets need original names, but must share one versioned source directory.
 mkdir "$stage/controller"
 for file in cover.py index.html app.js styles.css;do
   mv "$stage/cover-$file" "$stage/controller/$file"
 done
 python3 - "$stage" <<'PY'
from pathlib import Path
import ast,subprocess,sys
p=Path(sys.argv[1])
for f in (p/"vision.py",p/"controller/cover.py"):
    ast.parse(f.read_text(),filename=str(f))
    print("PASS: Python syntax",f.name)
for f in ("app.js","controller/app.js"):
    if subprocess.run(["sh","-c","command -v node >/dev/null"]).returncode==0:
        subprocess.run(["node","--check",str(p/f)],check=True)
sys.path.insert(0,str(p))
import vision
vision.selftest()
sys.path.insert(0,str(p/"controller"))
import cover
assert cover.FONT, "No system font found"
# Generate one synthetic cover frame without using the physical display.
g=cover.ffplay_graph()
r=subprocess.run(["ffmpeg","-nostdin","-hide_banner","-loglevel","error",
    "-f","lavfi","-i",g,"-frames:v","1","-f","null","-"],
    stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,timeout=12)
if r.returncode:
    raise SystemExit("FAIL: advert cover lavfi pipeline: "+r.stderr.decode(errors="replace")[-2500:])
print("PASS: visual cover indeterminate progress frame renders.")
PY
 stamp=$(date +%Y%m%d-%H%M%S)
 release="$ROOT/release-$stamp-$$"
 install -d -m 755 "$release"
 install -d -m 755 "$release/controller"
 for file in vision.py index.html style.css app.js;do
   install -o root -g root -m 644 "$stage/$file" "$release/$file"
 done
 for file in cover.py index.html app.js styles.css;do
   install -o root -g root -m 644 "$stage/controller/$file" "$release/controller/$file"
 done
 sha256sum "$release"/* "$release"/controller/* 2>/dev/null | grep -v '/controller$' || true
 ln -s "$release" "$ROOT/.new.$$"
 mv -Tf "$ROOT/.new.$$" "$ROOT/current"
 if [[ -f "$VISION_UNIT" ]];then cp -a "$VISION_UNIT" "$VISION_UNIT.before-$stamp";fi
 if [[ -f "$COVER_UNIT" ]];then cp -a "$COVER_UNIT" "$COVER_UNIT.before-$stamp";fi
 cat >"$VISION_UNIT" <<'UNIT'
[Unit]
Description=VEYRA provider advert-image recognition and template trainer (observe first)
After=veyra-virtual-loopback-v01.service
Requires=veyra-virtual-loopback-v01.service

[Service]
Type=simple
User=veyra
Group=veyra
WorkingDirectory=/opt/veyra/advision-v071/current
Environment=PYTHONDONTWRITEBYTECODE=1
Environment=VEYRA_ADVISION_DATA=/var/lib/veyra/advision-v071
ExecStart=/usr/bin/python3 /opt/veyra/advision-v071/current/vision.py
Restart=on-failure
RestartSec=3
NoNewPrivileges=yes
PrivateTmp=yes
UMask=0077
ProtectSystem=strict
ReadWritePaths=/var/lib/veyra/advision-v071
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX
CapabilityBoundingSet=
LockPersonality=yes
[Install]
WantedBy=multi-user.target
UNIT
 cat >"$COVER_UNIT" <<'UNIT'
[Unit]
Description=VEYRA recogniser-triggered TV advert cover, no break-length assumptions
After=veyra-kiosk.service

[Service]
Type=simple
WorkingDirectory=/opt/veyra/advision-v071/current/controller
ExecStart=/usr/bin/python3 /opt/veyra/advision-v071/current/controller/cover.py
ExecStopPost=-/usr/bin/python3 /opt/veyra/advision-v071/current/controller/cover.py recover
Restart=on-failure
RestartSec=3
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ReadWritePaths=/run /tmp
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX
UMask=0077
KillMode=mixed
TimeoutStopSec=6
[Install]
WantedBy=multi-user.target
UNIT
 chmod 644 "$VISION_UNIT" "$COVER_UNIT"
 systemctl daemon-reload
 # Restart ONLY the local cover controller; NEVER the underlying ITVX player or Chrome.
 systemctl enable --now "$VISION"
 if systemctl is-active --quiet "$COVER";then
   systemctl restart "$COVER"
 else
   systemctl enable --now "$COVER"
 fi
 for i in $(seq 1 25);do
  if curl -fsS --max-time 2 http://127.0.0.1:8774/api/state >/dev/null &&
     curl -fsS --max-time 2 http://127.0.0.1:8773/api/status >/dev/null;then
    echo 'PASS: trained visual recogniser (observation mode) and indefinite cover controller online.'
    echo 'TRAINING UI: http://127.0.0.1:8774/'
    echo 'TV COVER UI: http://127.0.0.1:8773/'
    echo 'Only the cover controller was restarted. Existing browser and player untouched.'
    return 0
  fi
  sleep .3
 done
 journalctl -u "$VISION" -u "$COVER" -n 30 --no-pager || true
 echo 'Detector/controller health unavailable; existing ITVX Chrome and VNC remain unaffected.'
 return 4
}
status(){
 for unit in "$VISION" "$COVER" veyra-kiosk.service veyra-virtual-loopback-v01.service veyra-itvx-vnc-v01.service;do
    echo "$unit: $(systemctl is-active "$unit" 2>/dev/null || true)"
 done
 echo '=== Vision ==='
 curl -fsS --max-time 3 http://127.0.0.1:8774/api/state || true
 echo
 echo '=== Cover ==='
 curl -fsS --max-time 3 http://127.0.0.1:8773/api/status || true
 echo
}
observe(){
 curl -fsS --max-time 4 -H 'X-Veyra-Visual: labelled-by-operator' -H 'Content-Type: application/json' -d '{"mode":"observe"}' \
    http://127.0.0.1:8774/api/mode
 echo
}
uncover(){
 curl -fsS --max-time 4 -H 'X-Veyra-Control: ad-cover-v070' -H 'Content-Type: application/json' -d '{}' \
   http://127.0.0.1:8773/api/end
 echo
}
case "$ACTION" in
 preflight)preflight;;
 install)install_app;;
 status)status;;
 observe)observe;;
 uncover)uncover;;
 *)echo 'Usage: sudo bash script {preflight|install|status|observe|uncover}';exit 2;;
esac
