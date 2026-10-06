#!/usr/bin/env bash
set -u
echo "=== NODE C GITHUB RUNNER SSH DISCOVERY ==="
echo "home=$HOME user=$(whoami) host=$(hostname)"
date -Is

echo
echo "runner ssh:"
ls -la "$HOME/.ssh" 2>/dev/null || true
echo "-- config --"
sed -n '1,240p' "$HOME/.ssh/config" 2>/dev/null || true
echo "-- public keys --"
for f in "$HOME"/.ssh/*.pub; do [ -f "$f" ] && { echo "FILE=$f"; cat "$f"; }; done

echo
echo "ssh aliases:"
for h in nodea nodeb node-c node-a node-b 10.10.10.235 10.10.10.226; do
  echo "--- $h ---"
  ssh -G "$h" 2>/dev/null | grep -E '^(hostname|user|identityfile|proxyjump|proxycommand) ' | head -20 || true
done

echo
echo "candidate gateway helpers:"
find /usr/local/bin /usr/local/sbin /opt /srv "$HOME" -maxdepth 4 -type f \
  \( -iname '*gateway*' -o -iname '*nodeb*' -o -iname '*nodea*' -o -iname '*ssh*' \) \
  -print 2>/dev/null | head -150 || true

echo
echo "network:"
ip route 2>/dev/null || true
ip -brief addr 2>/dev/null || true

echo
echo "known host connectivity by aliases:"
for h in nodeb nodea; do
  echo "--- $h ---"
  ssh -o BatchMode=yes -o ConnectTimeout=5 "$h" 'echo CONNECTED; hostname; whoami' 2>&1 || true
done
