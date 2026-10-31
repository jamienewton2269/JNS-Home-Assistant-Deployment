#!/usr/bin/env bash
set -Eeuo pipefail
# Run only on the existing Node C self-hosted runner.
# Never destroy or alter VM219, VM119, or an occupied CT ID.
ssh -o BatchMode=yes -o ConnectTimeout=8 -o StrictHostKeyChecking=accept-new root@nodeb.home.arpa 'bash -s' <<'REMOTE'
set -Eeuo pipefail
CTID=221
TEMPLATE=local:vztmpl/debian-13-standard_13.6-1_amd64.tar.zst
if qm config "$CTID" >/dev/null 2>&1; then exit 20; fi
if pct config "$CTID" >/dev/null 2>&1; then
  test "$(pct config "$CTID" | sed -n 's/^hostname: //p')" = house-audio-b || exit 21
else
  pct create "$CTID" "$TEMPLATE" --hostname house-audio-b --ostype debian --arch amd64 --cores 1 --memory 256 --swap 256 --rootfs local-lvm:4 --net0 'name=eth0,bridge=vmbr0,ip=dhcp,ip6=auto' --unprivileged 1 --onboot 1
fi
pct status "$CTID" | grep -q running || pct start "$CTID"
pct exec "$CTID" -- bash -euc '
export DEBIAN_FRONTEND=noninteractive
apt-get update -o Acquire::http::No-Cache=true -o Acquire::https::No-Cache=true
apt-get install -y --no-install-recommends mpd mpc sudo ca-certificates
id jnsadmin >/dev/null 2>&1 || useradd -m -s /bin/bash -G sudo jnsadmin
echo "jnsadmin:\$6\$V555Yd9PK66s6Ek4\$25o1JvRD/L87uOxVY2774kPNz3j1/iR7ZmHeKAd6KTdFfVW1OQQRoXf9bCjBj.zMTVvroecU36FzC4IRMB5Uz0" | chpasswd -e
install -d -o mpd -g audio /var/lib/mpd/music /var/lib/mpd/playlists
cat >/etc/mpd.conf <<EOF
music_directory "/var/lib/mpd/music"
playlist_directory "/var/lib/mpd/playlists"
db_file "/var/lib/mpd/tag_cache"
log_file "syslog"
pid_file "/run/mpd/pid"
state_file "/var/lib/mpd/state"
sticker_file "/var/lib/mpd/sticker.sql"
user "mpd"
bind_to_address "0.0.0.0"
port "6600"
auto_update "yes"
audio_output {
 type "httpd"
 name "House Audio B Stream"
 encoder "vorbis"
 port "8000"
 bitrate "128"
 format "44100:16:2"
 always_on "yes"
}
EOF
systemctl enable --now mpd
systemctl restart mpd
systemctl is-active --quiet mpd
mpc -h 127.0.0.1 -p 6600 status
'
echo "CT221_CREATED"
pct config "$CTID"
pct exec "$CTID" -- systemctl is-active mpd
REMOTE
