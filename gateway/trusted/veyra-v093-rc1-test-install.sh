#!/usr/bin/env bash
# Veyra v0.9.3-rc1: staged Lenovo application test update.
# Keeps Cage, seatd, systemd kiosk service, and browser-profile directories untouched.
set -Eeuo pipefail
if [ "$(id -u)" != 0 ]; then echo 'Run as sudo/root'; exit 2; fi
say(){ printf '%s\n' "$*"; }
root=/opt/veyra
test -f "$root/veyra/view.py" && test -f "$root/veyra/kiosk.py" || { say 'Veyra runtime not found'; exit 3; }
systemctl is-active --quiet veyra-kiosk.service || { say 'STOP: kiosk currently inactive; preserve working graphics'; exit 4; }
if ! curl -fsS --max-time 3 -o /dev/null http://127.0.0.1:8766/; then say 'STOP: local Veyra dashboard not responding'; exit 5; fi
mkdir -p /var/backups/veyra-releases
stamp="$(date +%Y%m%d-%H%M%S)"
backup="/var/backups/veyra-releases/v0.9.3-rc1-$stamp.tar.gz"
tar -czf "$backup" -C / opt/veyra/veyra/view.py opt/veyra/veyra/kiosk.py opt/veyra/browser-extension
sha256sum "$backup" > "$backup.sha256"
say "Rollback source archive: $backup"
# Existing home controller must be installed before we can safely terminate a provider browser.
if ! grep -q 'veyra-nav-home-v1' "$root/veyra/kiosk.py"; then
 say 'STOP: known-good Veyra Home controller is missing; install and validate navigation hotfix first.'
 exit 6
fi
# Download the exact source of the tested UI update into a temporary file.
tmp=$(mktemp)
trap 'rm -f "$tmp"' EXIT
url='https://raw.githubusercontent.com/jamienewton2269/JNS-Home-Assistant-Deployment/main/gateway/trusted/veyra-programme-discovery-v1.sh'
curl --fail --location --silent --show-error --connect-timeout 8 --max-time 30 "$url" -o "$tmp"
bash -n "$tmp"
say 'Installing programme title suggestions...'
bash "$tmp"
# Chrome managed policy: suppress native password-saving prompt.
# Browser logins and provider profiles are not removed.
policy=/etc/opt/chrome/policies/managed
mkdir -p "$policy"
if [ -f "$policy/veyra-passwords.json" ]; then
 cp -a "$policy/veyra-passwords.json" "$policy/veyra-passwords.json.before-$stamp"
fi
printf '%s\n' '{"PasswordManagerEnabled":false,"CredentialsEnableService":false}' > "$policy/veyra-passwords.json"
chmod 644 "$policy/veyra-passwords.json"
# Credential vault NOT enabled: never store plaintext passwords or capture provider forms.
# Watch-history capture NOT enabled until consent, robust provider detection, and encrypted storage.
say 'Requesting Veyra Home from browser supervisor...'
code=$(curl -sS --max-time 8 -o /dev/null -w '%{http_code}' -X POST http://127.0.0.1:8767/home)
[ "$code" = 204 ] || { say "Home endpoint returned $code"; exit 7; }
sleep 5
say '=== RELEASE CHECK ==='
say 'Version: v0.9.3-rc1 test features'
systemctl show veyra-kiosk.service -p ActiveState -p Result -p Restart
curl -s -o /dev/null -w 'Dashboard HTTP %{http_code}\n' --max-time 3 http://127.0.0.1:8766/
say 'Expected: Veyra Home visible. Test Add Programme suggestions; provider links may need manual verification.'
say 'NOT SHIPPED: universal Cage-level Escape, encrypted shared account vault, automatic watch tracking, live availability across all streaming providers.'
say "Source rollback archive: $backup"
