#!/usr/bin/env bash
# Veyra Sway navigation v1.1: Back = browser's previous page; Home = Veyra.
# Staged graphics, Cage fallback and provider profile data are untouched.
set -Eeuo pipefail
[ "$(id -u)" = 0 ] || { echo 'Run via sudo'; exit 2; }
test -f /etc/veyra/sway.conf
test -f /opt/veyra/scripts/veyra-nav
grep -q 'bindsym --no-repeat Escape exec /opt/veyra/scripts/veyra-nav back' /etc/veyra/sway.conf
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends wtype
backup=/var/backups/veyra-sway-nav-$(date +%Y%m%d-%H%M%S)
mkdir -p "$backup"
cp -a /opt/veyra/scripts/veyra-nav /etc/veyra/sway.conf "$backup/"
cat >/opt/veyra/scripts/veyra-nav <<'NAV'
#!/usr/bin/env bash
set -euo pipefail
case "${1:-home}" in
 home)
  code=$(curl -sS --max-time 5 -o /dev/null -w '%{http_code}' -X POST http://127.0.0.1:8767/home)
  [ "$code" = 204 ] || { echo "Home request HTTP $code" >&2; exit 1; }
  ;;
 back)
  # Issued by compositor/Waybar, not provider JavaScript.
  # Alt+Left asks Chrome to move to its previous top-level history entry.
  # Does not traverse history across separate Chrome profile sessions.
  /usr/bin/wtype -M alt -k Left -m alt
  ;;
 *) exit 2;;
esac
NAV
chmod 755 /opt/veyra/scripts/veyra-nav
bash -n /opt/veyra/scripts/veyra-nav
echo 'VEYRA_SWAY_NAV_BACK_V1_1_INSTALLED'
echo "Rollback copy: $backup"
echo 'No compositor restart needed; test Back within ITVX/E4 then Home direct.'
echo 'Limitation: Back at first provider page cannot cross Chrome-session history; next update must add app-level stack.'
