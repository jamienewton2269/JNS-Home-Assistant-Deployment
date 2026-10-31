#!/usr/bin/env bash
set -euo pipefail
ssh -o BatchMode=yes -o ConnectTimeout=8 root@nodeb.home.arpa 'bash -s' <<'REMOTE'
set -u
echo 'JNS_AUDIO_CHECK_BEGIN'
echo '=== TARGET OWNERSHIP ==='
pct config 221 | grep -E '^(hostname|net0|unprivileged):' || true
echo '=== MPD SERVICE ==='
pct exec 221 -- sh -c 'systemctl is-active mpd; systemctl show mpd -p ExecMainStatus -p ActiveState -p SubState -p NRestarts --no-pager; mpc status; mpc outputs' 2>&1 | tail -30 || true
echo '=== MPD TCP LISTEN ==='
pct exec 221 -- sh -c 'ss -lntp | grep -E ":(6600|8000) " || true; grep -A14 -B2 "type *\"httpd\"" /etc/mpd.conf | sed -E "s/^([[:space:]]*password[[:space:]]+).*/\\1[REDACTED]/"' 2>&1 | tail -35 || true
echo '=== MPD LOG ERROR SUMMARY ==='
pct exec 221 -- sh -c 'journalctl -u mpd --since "-45 min" --no-pager | grep -iE "error|fail|stream|bind|output|format|encoder|httpd|mixer|listen" | tail -22' 2>&1 | tail -30 || true
echo '=== MPD PORT CHECK FROM NODE B ==='
for address in house-audio-b.home.arpa; do
getent ahostsv4 "$address" | head -2 || true
curl -sSI --max-time 3 -o /dev/null -w "JNS_AUDIO_HTTP8000 %{http_code} connect=%{time_connect}\n" "http://$address:8000/" || true
done
echo '=== RECEIVER & BLUETOOTH ==='
systemctl is-active jns-audio-receiver || true
systemctl show jns-audio-receiver -p ActiveState -p SubState -p NRestarts --no-pager || true
bluetoothctl info 91:56:5F:5E:55:47 2>/dev/null | grep -E 'Connected:|Paired:|Trusted:' || true
echo '=== HA GENERAL MPD ENTRY ==='
qm guest exec 905 -- /usr/bin/jq -c '.data.entries[]|select(.domain=="mpd")|{entry_id,host:.data.host,port:.data.port,disabled_by,configured_password:(.data.password!=null and .data.password!="")}' /mnt/data/supervisor/homeassistant/.storage/core.config_entries 2>&1 | tail -14 || true
echo '=== HA GENERAL MPD LOG ERRORS ==='
qm guest exec 905 -- sh -c 'grep -iE "mpd|music_player_daemon|Music Player Daemon" /mnt/data/supervisor/homeassistant/home-assistant.log 2>/dev/null | tail -12' 2>&1 | tail -18 || true
echo 'JNS_AUDIO_READONLY_CHECK_COMPLETE'
REMOTE
