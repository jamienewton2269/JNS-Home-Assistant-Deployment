#!/usr/bin/env bash
# Scoped Node C -> Node B House Audio B receiver repair (only).
# MPD/HA clock/HA integrations, alarms, DNS and Bluetooth trust are untouched.
set -Eeuo pipefail
ssh -o BatchMode=yes -o ConnectTimeout=8 root@nodeb.home.arpa 'bash -s' <<'REMOTE'
set -Eeuo pipefail
CTID=221
target=/usr/local/sbin/jns-audio-receiver
unit=jns-audio-receiver.service
speaker=91:56:5F:5E:55:47
test "$(pct config "$CTID" | sed -n 's/^hostname: //p')" = house-audio-b
pct exec "$CTID" -- systemctl is-active --quiet mpd
test -x "$target"
systemctl cat "$unit" | grep -Fq "ExecStart=$target"
grep -Fq 'exec ogg123' "$target"
grep -Fq 'pct exec 221' "$target"
command -v ogg123 >/dev/null
getent ahostsv4 house-audio-b.home.arpa >/dev/null
bluetoothctl info "$speaker" | grep -Fq 'Connected: yes'
original_sha="$(sha256sum "$target" | cut -d' ' -f1)"
backup="$target.before-resilient-clock-20261031"
test ! -e "$backup"
cp -p "$target" "$backup"
test "$(sha256sum "$backup" | cut -d' ' -f1)" = "$original_sha"
echo JNS_RECEIVER_BACKUP_VALIDATED
tmp="$(mktemp /usr/local/sbin/.jns-audio-receiver.XXXXXX)"
rollback() {
  echo JNS_RECEIVER_ROLLBACK_START
  cp -p "$backup" "$target"
  systemctl restart "$unit" || true
  echo JNS_RECEIVER_ROLLBACK_COMPLETED
}
trap 'rm -f "$tmp"' EXIT
cat > "$tmp" <<'SCRIPT'
#!/usr/bin/env bash
# Stream port opens only during Westminster playback on this MPD build.
# Keep a tiny systemd-managed waiter instead of restarting the unit every 10s.
set -uo pipefail
STREAM=house-audio-b.home.arpa
SPEAKER=91:56:5F:5E:55:47
bluetoothctl connect "$SPEAKER" >/dev/null 2>&1 || true
while :; do
  if timeout 2 bash -c 'exec 3<>/dev/tcp/house-audio-b.home.arpa/8000; exec 3>&-' >/dev/null 2>&1; then
    ogg123 -q -d alsa -o 'dev:bluealsa:DEV=91:56:5F:5E:55:47,PROFILE=a2dp' "http://$STREAM:8000/" || true
  fi
  sleep 0.6
done
SCRIPT
bash -n "$tmp"
chmod 0755 "$tmp"
chown --reference="$target" "$tmp"
test "$(sha256sum "$target" | cut -d' ' -f1)" = "$original_sha"
mv -f "$tmp" "$target"
echo JNS_RECEIVER_REPAIRED_FILE
if ! systemctl restart "$unit"; then rollback;exit 40;fi
sleep 3
if ! systemctl is-active --quiet "$unit";then rollback;exit 41;fi
before="$(systemctl show "$unit" -p NRestarts --value)"
sleep 5
after="$(systemctl show "$unit" -p NRestarts --value)"
if [ "$before" != "$after" ];then rollback;exit 42;fi
echo JNS_RECEIVER_IDLE_NO_RESTARTS
# Real, original 12-second chime acceptance. This test is intentionally audible.
pct exec "$CTID" -- mpc clear >/dev/null
pct exec "$CTID" -- mpc repeat off >/dev/null
pct exec "$CTID" -- mpc load jns_westminster_half >/dev/null
pct exec "$CTID" -- mpc play >/dev/null
sleep 2
if ! pct exec "$CTID" -- sh -c 'ss -lnt | grep -q ":8000 "';then
  echo JNS_RECEIVER_STREAM_NOT_OPEN;rollback;exit 43
fi
if ! pgrep -x ogg123 >/dev/null;then
  echo JNS_RECEIVER_NOT_ATTACHED_DURING_CHIME;rollback;exit 44
fi
echo JNS_CLOCK_AUDIO_ATTACHED_DURING_CHIME
sleep 11
systemctl is-active --quiet "$unit" || { rollback;exit 45; }
last="$(systemctl show "$unit" -p NRestarts --value)"
test "$last" = "$after" || { rollback;exit 46; }
echo JNS_CLOCK_RECEIVER_REPAIRED_AND_VERIFIED
echo JNS_CLOCK_SPEAKER_CONNECTION_STATUS
bluetoothctl info "$speaker" | grep 'Connected:' || true
REMOTE
