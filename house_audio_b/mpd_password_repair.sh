#!/usr/bin/env bash
set -Eeuo pipefail
# Guarded HA-General MPD integration repair, only empty password field removal.
ssh -o BatchMode=yes -o ConnectTimeout=8 root@nodeb.home.arpa 'bash -s' <<'REMOTE'
set -Eeuo pipefail
VM=905
CT=221
ENTRY=01M4VJYJGS81KFN0FNGJJWM39B
FILE=/mnt/data/supervisor/homeassistant/.storage/core.config_entries
BACKUP="$FILE.before-jns-mpd-auth-20261031-1818"
TMP="$FILE.jns-no-password-stage"
core_stopped=0
patch_done=0
finished=0
qga() {
  local raw
  raw="$(qm guest exec "$VM" --timeout 150 -- "$@")"
  jq -e '(.exited == 1 or .exited == true) and (.exitcode == 0)' <<<"$raw" >/dev/null
  jq -r '."out-data" // ""' <<<"$raw"
}
recovery() {
  local rc=$?
  trap - EXIT
  if [ "$finished" != 1 ] && { [ "$core_stopped" = 1 ] || [ "$patch_done" = 1 ]; }; then
    if [ "$patch_done" = 1 ]; then
      echo JNS_CLOCK_MPD_AUTH_ROLLBACK_ATTEMPTED
      qga ha core stop >/dev/null 2>&1 || true
      qga /bin/sh -c "test -f '$BACKUP' && /bin/cp -p '$BACKUP' '$FILE' && /usr/bin/jq -e '.data.entries | type == \"array\"' '$FILE' >/dev/null" || true
    fi
    qga ha core start || true
  fi
  exit "$rc"
}
trap recovery EXIT
test "$(pct config "$CT" | sed -n 's/^hostname: //p')" = "house-audio-b"
pct exec "$CT" -- systemctl is-active --quiet mpd
pct exec "$CT" -- sh -c '! grep -Eq "^[[:space:]]*password[[:space:]]+" /etc/mpd.conf && mpc -h 127.0.0.1 -p 6600 status >/dev/null'
qga /usr/bin/jq -e \
  --arg id "$ENTRY" --arg host house-audio-b.home.arpa \
  '([.data.entries[] | select(.entry_id == $id and .domain == "mpd" and .data.host == $host and .data.port == 6600 and .disabled_by == null and .data.password == "" and (.data | has("password")))] | length) == 1' \
  "$FILE" >/dev/null
qga /usr/bin/jq -e \
  --arg id "$ENTRY" \
  '([.data.entities[] | select(.entity_id == "media_player.music_player_daemon" and .platform == "mpd" and .config_entry_id == $id and .disabled_by == null)] | length) == 1' \
  /mnt/data/supervisor/homeassistant/.storage/core.entity_registry >/dev/null
qga docker inspect --format '{{.State.Running}}' homeassistant | grep -qx true
echo JNS_CLOCK_MPD_AUTH_PREFLIGHT_PASSED
qga ha core stop >/dev/null
core_stopped=1
qga /bin/sh -c "set -eu; test -f '$FILE' && test ! -e '$BACKUP' && /bin/cp -p '$FILE' '$BACKUP'; test -s '$BACKUP'; test ! -e '$TMP'" >/dev/null
echo JNS_CLOCK_MPD_AUTH_BACKUP_VERIFIED
qga /bin/sh -c "set -eu;
 /bin/cp -p '$BACKUP' '$TMP';
 /usr/bin/jq --arg id '$ENTRY' '(.data.entries[] | select(.entry_id == \$id and .domain == \"mpd\")) |= del(.data.password)' '$BACKUP' > '$TMP';
 /usr/bin/jq -e --arg id '$ENTRY' '([.data.entries[] | select(.entry_id == \$id and .domain == \"mpd\" and .data.host == \"house-audio-b.home.arpa\" and (.data | has(\"password\") | not))] | length) == 1' '$TMP' >/dev/null;
 test \"\$(sha256sum '$BACKUP' | cut -d' ' -f1)\" != \"\$(sha256sum '$TMP' | cut -d' ' -f1)\";
 /bin/mv -f '$TMP' '$FILE';
 /usr/bin/jq -e '.data.entries | type == \"array\"' '$FILE' >/dev/null" >/dev/null
patch_done=1
echo JNS_CLOCK_MPD_AUTH_EMPTY_FIELD_REMOVED
qga ha core start >/dev/null
core_stopped=0
ok=0
for i in $(seq 1 25); do
  if qga docker inspect --format '{{.State.Running}}' homeassistant 2>/dev/null | grep -qx true; then ok=1;break;fi
  sleep 4
done
if [ "$ok" != 1 ]; then
  core_stopped=1
  echo JNS_CLOCK_MPD_AUTH_CORE_START_NOT_VERIFIED
  exit 20
fi
qga /usr/bin/jq -e --arg id "$ENTRY" \
  '([.data.entries[] | select(.entry_id == $id and .domain == "mpd" and .disabled_by == null and .data.host == "house-audio-b.home.arpa" and (.data | has("password") | not))] | length) == 1' \
  "$FILE" >/dev/null
qga docker exec homeassistant python3 -c \
  'import socket; s=socket.create_connection(("house-audio-b.home.arpa",6600),timeout=8);s.settimeout(8); assert s.recv(32).startswith(b"OK MPD"),"Missing MPD greeting";s.sendall(b"status\n");out=s.recv(512);assert b"volume:" in out or b"state:" in out, "MPD status unavailable";s.close();print("JNS_CLOCK_MPD_ANONYMOUS_SESSION_OK")'
finished=1
echo JNS_CLOCK_MPD_AUTH_REPAIRED_CORE_RUNNING
echo JNS_CLOCK_MPD_AUTH_CONFIG_ENTRY_VALIDATED
REMOTE