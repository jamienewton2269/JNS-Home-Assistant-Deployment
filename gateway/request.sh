#!/usr/bin/env bash
set -euo pipefail
echo "=== RECOVER OLD HA900 CLOCK READ-ONLY/ISOLATED ==="
date -Is
ssh -o BatchMode=yes nodea 'bash -s' <<'REMOTE'
set -euo pipefail
ID=900
orig=$(qm config "$ID" | sed -n 's/^net0: //p')
echo "ORIGINAL_NET0=$orig"
was=$(qm status "$ID" | awk '{print $2}')
echo "ORIGINAL_STATUS=$was"
cleanup() {
  if [ "$(qm status "$ID" | awk '{print $2}')" = running ]; then qm stop "$ID" --skiplock 1 >/dev/null 2>&1 || true; fi
  qm set "$ID" --net0 "$orig" >/dev/null 2>&1 || true
}
trap cleanup EXIT
if [[ "$orig" == *link_down=* ]]; then
  iso="$orig"
else
  iso="$orig,link_down=1"
fi
qm set "$ID" --net0 "$iso" >/dev/null
qm start "$ID"
for i in $(seq 1 30); do
  if qm guest cmd "$ID" ping >/dev/null 2>&1; then break; fi
  sleep 2
done
qm guest cmd "$ID" ping >/dev/null
echo "QGA READY"
qm guest exec "$ID" -- /bin/bash -lc 'echo CLOCK_FILES; find /mnt/data/supervisor/homeassistant/media /mnt/data/supervisor/homeassistant/www /mnt/data/supervisor/homeassistant -maxdepth 5 -type f 2>/dev/null | grep -Ei "westminster|chime|bird|clock|tweet" | head -200; echo AUTOMATION_MATCHES; grep -RniE "westminster|chime|bird|clock|tweet" /mnt/data/supervisor/homeassistant/*.yaml /mnt/data/supervisor/homeassistant/packages 2>/dev/null | head -250 || true'
REMOTE
