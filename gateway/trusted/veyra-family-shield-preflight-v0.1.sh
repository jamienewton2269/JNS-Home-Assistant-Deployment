#!/usr/bin/env bash
# Veyra Family Shield v0.1 - safe read-only preflight / package staging only
set -Eeuo pipefail
MODE=${1:-preflight}
EXT=/opt/veyra/browser-extension
DEST=/opt/veyra/staged/family-shield-v0.1
case "$MODE" in
preflight)
  echo '=== Veyra Family Shield preflight (READ ONLY) ==='
  echo '=== Kiosk ==='
  systemctl is-active veyra-kiosk.service || :
  echo '=== Extension manifest ==='
  if [ -f "$EXT/manifest.json" ]; then
    python3 - "$EXT/manifest.json" <<'PY'
import json,sys
p=json.load(open(sys.argv[1]))
print('Manifest version:', p.get('manifest_version'))
print('Background:',p.get('background',{}))
print('Permissions:',p.get('permissions',[]))
print('Content scripts:',[(c.get('matches'),c.get('js')) for c in p.get('content_scripts',[])])
PY
  else echo 'MISSING manifest';fi
  echo '=== Media stream controls ==='
  command -v pactl || :
  echo '=== Audio sinks (read-only) ==='
  pactl list short sinks 2>&1 || :
  echo '=== Running provider processes ==='
  ps -eo user,pid,args | grep -E '[c]hrome .*provider-profiles|[c]age --' | cut -c1-200 || :
  echo '=== DRM/CDM, protected content and automatic ad boundaries not changed ==='
 ;;
stage)
  [ "$(id -u)" = 0 ] || { echo 'stage requires sudo';exit 2; }
  install -d -m 0755 "$DEST"
  cat >"$DEST/holding.html" <<'HTML'
<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Veyra family shield</title>
<style>html,body{margin:0;height:100%;background:#070c12;color:#eef3f6;font-family:sans-serif}
main{height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center}
h1{letter-spacing:.35em;font-size:clamp(28px,5vw,65px);font-weight:400;margin:.3em}
p{font-size:clamp(17px,2vw,26px);text-align:center}</style></head>
<body><main><h1>VEYRA</h1><p>Picture and sound temporarily suppressed</p></main></body></html>
HTML
  cat >"$DEST/README.txt" <<'TXT'
Test staging only: this does not change Chrome, Cage, profiles, startup services,
or audio routing. Do not present this file in a small browser window and call it
a protective overlay: picture must be fully hidden and all audio streams muted
before a child-safe feature can be described as active.
Next step requires adapting a mute+cover transaction to the existing kiosk
extension/IPC, then verifying it on the physical display with rollback.
TXT
  chmod 644 "$DEST"/*
  echo "STAGED_ONLY: $DEST"
  echo 'No protection is active and the kiosk was not modified.'
 ;;
*) echo 'Usage: bash family-shield-v0.1.sh preflight | sudo bash family-shield-v0.1.sh stage'; exit 2;;
esac
