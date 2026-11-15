#!/usr/bin/env bash
set -Eeuo pipefail
echo '=== KEA BIND PRODUCTION READINESS INVENTORY ==='
date -u +%FT%TZ
for host in nodea nodeb; do
  echo "=== $host ==="
  ssh -o BatchMode=yes -o ConnectTimeout=8 "$host" '
    hostname
    for ct in 247 248; do
      if pct status "$ct" 2>/dev/null | grep -q running; then
        echo "=== CT $ct ==="
        pct exec "$ct" -- sh -c "for s in kea-dhcp4-server kea-dhcp6-server kea-dhcp-ddns-server bind9 named jns-dns; do systemctl is-active \"\$s\" 2>/dev/null || true; done; command -v kea-dhcp4 || true; command -v kea-dhcp6 || true; command -v named || true"
      fi
    done
  ' || echo "FAILED $host"
done
echo '=== END INVENTORY ==='
