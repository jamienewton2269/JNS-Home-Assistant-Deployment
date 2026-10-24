#!/usr/bin/env bash
# VEYRA OBS XSHM v1.3 source audit — strictly read-only.
set -Eeuo pipefail
BASE=/opt/veyra/obs-backend-v1/av-qa-v11
SCENE="$BASE/config/obs-studio/basic/scenes/VEYRA_QA.json"
LOG="$BASE/logs/obs-console.log"
echo '=== OBS SCENE / DISPLAY AUDIT ==='
for u in veyra-kiosk.service veyra-itvx-vnc-v01.service veyra-virtual-loopback-v01.service; do
  printf '%s=' "$u"; systemctl is-active "$u" || true
done
for n in 92 93; do
  test -S "/tmp/.X11-unix/X$n" && echo "DISPLAY:$n present" || echo "DISPLAY:$n absent"
done
if test -r "$SCENE"; then
  python3 - "$SCENE" <<'PY'
import json,sys
p=sys.argv[1]; d=json.load(open(p))
sources=d.get("sources",[])
byuuid={s.get("uuid"):s for s in sources}
print("scene:",d.get("current_scene"))
for s in sources:
    x=s.get("settings",{})
    print("source:",s.get("name"),"id:",s.get("id"),"versioned_id:",s.get("versioned_id"))
    if s.get("id")=="xshm_input_v2" or s.get("versioned_id")=="xshm_input_v2":
        print("xshm:",{k:x.get(k) for k in ("advanced","server","screen")})
    if s.get("id")=="scene":
        for item in x.get("items",[]):
            print("scene_item:",item.get("name"),"exists:",item.get("source_uuid") in byuuid,"visible:",item.get("visible"))
PY
else echo "SCENE_UNREADABLE: $SCENE"; fi
echo '=== OBS LAST SOURCE STARTUP ==='
if test -r "$LOG"; then
  grep -Ei 'xshm|scene|source|pulse|failed|error|OpenGL|llvmpipe' "$LOG" | tail -50 | cut -c 1-180 || true
else echo "LOG_UNREADABLE: $LOG"; fi
echo '=== END: no service or configuration changed ==='
