#!/usr/bin/env bash
# Veyra kiosk stale-navigation-port recovery. Install via: sudo bash THIS_FILE install
set -Eeuo pipefail
[ "$(id -u)" = 0 ] || { echo "Run as root using sudo"; exit 2; }
case "${1:-}" in
 install)
  install -d -m 755 /usr/local/libexec /var/lib/veyra-watchdog
  install -m 755 "$0" /usr/local/libexec/veyra-kiosk-watchdog
  cat >/etc/systemd/system/veyra-kiosk-watchdog.service <<'UNIT'
[Unit]
Description=Veyra kiosk bounded recovery watchdog
After=network.target
[Service]
Type=oneshot
ExecStart=/usr/local/libexec/veyra-kiosk-watchdog check
TimeoutStartSec=35
UNIT
  cat >/etc/systemd/system/veyra-kiosk-watchdog.timer <<'UNIT'
[Unit]
Description=Check Veyra kiosk health every minute
[Timer]
OnBootSec=90s
OnUnitInactiveSec=60s
AccuracySec=10s
Unit=veyra-kiosk-watchdog.service
[Install]
WantedBy=timers.target
UNIT
  systemctl daemon-reload
  systemctl enable --now veyra-kiosk-watchdog.timer
  echo "WATCHDOG_INSTALLED; no kiosk restart performed"
  systemctl --no-pager status veyra-kiosk-watchdog.timer || :
  ;;
 check)
  exec 9>/run/veyra-kiosk-watchdog.lock
  flock -n 9 || exit 0
  # Healthy means active AND one authoritative kiosk process exists.
  if systemctl is-active --quiet veyra-kiosk.service; then
    echo "VEYRA_OK: active; no action"; exit 0
  fi
  # Avoid intervening during deliberate maintenance or an in-progress restart.
  state=$(systemctl show veyra-kiosk.service -p ActiveState --value)
  case "$state" in activating|deactivating) echo "VEYRA_WAIT: $state"; exit 0;; esac
  # Limit to two automatic interventions in a rolling ten minutes.
  file=/var/lib/veyra-watchdog/restarts
  mkdir -p /var/lib/veyra-watchdog
  now=$(date +%s)
  if [ -f "$file" ]; then
    count=$(awk -v n="$now" '$1>n-600 {print $1}' "$file" | wc -l)
  else count=0; fi
  if [ "$count" -ge 2 ]; then
    echo "VEYRA_MANUAL_INTERVENTION: limit of 2 restarts/10min reached"
    exit 0
  fi
  # Detect local IPv4 navigation listener; only touch process with verified
  # executable argv of the expected Veyra kiosk, owned by 'veyra' user.
  owner=$(ss -H -ltnp '( sport = :8767 )' 2>/dev/null | sed -n 's/.*pid=\([0-9][0-9]*\).*/\1/p' | head -n1)
  if [ -n "$owner" ]; then
    cmd=$(tr '\0' ' ' <"/proc/$owner/cmdline" 2>/dev/null || :)
    uid=$(stat -c %u "/proc/$owner" 2>/dev/null || :)
    vuid=$(id -u veyra)
    if [ "$uid" != "$vuid" ] || [[ "$cmd" != *"/opt/veyra/.venv/bin/python -m veyra.kiosk"* ]]; then
      echo "VEYRA_BLOCKED: 8767 held by unexpected PID=$owner; no termination"
      exit 0
    fi
    # Do not kill a process that belongs to the active service cgroup.
    cg=$(cat "/proc/$owner/cgroup" 2>/dev/null || :)
    if [[ "$cg" == *"/veyra-kiosk.service"* ]]; then
      echo "VEYRA_WAIT: 8767 owned by kiosk service PID=$owner; no termination"
      exit 0
    fi
    echo "VEYRA_STALE_KIOSK: pid=$owner, sending TERM"
    kill -TERM "$owner"
    for i in 1 2 3 4 5; do
      kill -0 "$owner" 2>/dev/null || break
      sleep 1
    done
    if kill -0 "$owner" 2>/dev/null; then
      echo "VEYRA_BLOCKED: stale owner did not exit; no force kill"
      exit 0
    fi
  fi
  # Do not run if the expected nav port is still in use.
  if ss -H -ltn '( sport = :8767 )' | grep -q .; then
    echo "VEYRA_BLOCKED: port 8767 still bound; no restart"; exit 0
  fi
  printf '%s\n' "$now" >>"$file"
  awk -v n="$now" '$1>n-600 {print $1}' "$file" >"$file.tmp"
  mv "$file.tmp" "$file"
  echo "VEYRA_RECOVERY: reset-failed then start"
  systemctl reset-failed veyra-kiosk.service
  systemctl start --no-block veyra-kiosk.service
  ;;
 *) echo 'Usage: sudo bash script install | sudo /usr/local/libexec/veyra-kiosk-watchdog check'; exit 2;;
esac
