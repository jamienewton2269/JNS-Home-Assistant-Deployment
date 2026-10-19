#!/usr/bin/env bash
# Veyra source capture for consolidated next release. Read-only; no restarts.
set -Eeuo pipefail
if [[ $(id -u) -ne 0 ]]; then echo 'Run with sudo'; exit 2; fi
src=/opt/veyra
test -f "$src/veyra/app.py" && test -f "$src/veyra/kiosk.py" && test -f "$src/veyra/view.py" || { echo 'Expected Veyra source not found'; exit 3; }
userhome=/home/jnsadmin
test -d "$userhome" || { echo 'jnsadmin home missing'; exit 4; }
out="$userhome/veyra-source-for-next-release-$(date +%Y%m%d-%H%M%S).tar.gz"
tmp=$(mktemp -d /tmp/veyra-source.XXXXXXXX)
trap 'rm -rf -- "$tmp"' EXIT
mkdir -p "$tmp/source" "$tmp/config" "$tmp/status"
# Limit capture to source, scripts and extension code; do not include media, venv, vendor Chrome or browser state.
for directory in veyra scripts browser-extension; do
  if [[ -d "$src/$directory" ]]; then
    mkdir -p "$tmp/source/$directory"
    find "$src/$directory" -type f \( -name '*.py' -o -name '*.js' -o -name '*.json' -o -name '*.html' -o -name '*.css' -o -name '*.sh' -o -name '*.service' \) \
      ! -name '*secret*' ! -name '*token*' ! -name '*credential*' ! -name '*.pyc' -print0 |
    while IFS= read -r -d '' file; do
      relative="${file#$src/}"
      mkdir -p "$tmp/source/$(dirname "$relative")"
      cp -- "$file" "$tmp/source/$relative"
    done
  fi
done
# Inspect exact service baseline; useful for packaging graphics fixes.
systemctl cat veyra-kiosk.service > "$tmp/config/kiosk-unit.txt" 2>&1 || :
systemctl show veyra-kiosk.service -p ActiveState -p Result -p Restart -p WorkingDirectory -p Environment > "$tmp/status/kiosk.txt" 2>&1 || :
id veyra > "$tmp/status/veyra-id.txt" 2>&1 || :
cat > "$tmp/README.txt" <<'TXT'
Source files from Veyra laptop, for next release development.
Contains application Python, HTML/JS/CSS, shell scripts, browser extension, and systemd kiosk unit.
Excluded by design: /var/lib/veyra, Chrome profiles, login cookies, .venv, vendored Chrome, /etc/veyra/veyra.env, database content.
Review before sharing: an application source file could still contain hard-coded secrets.
This script DOES NOT restart Chrome, Cage or systemd services.
TXT
tar -czf "$out" -C "$tmp" .
sha256sum "$out" > "$out.sha256"
chown jnsadmin:jnsadmin "$out" "$out.sha256"
chmod 600 "$out" "$out.sha256"
echo "SOURCE_CAPTURE_PASS"
ls -lh "$out" "$out.sha256"
echo "Download with FileZilla from /home/jnsadmin, review and upload archive into ChatGPT."
