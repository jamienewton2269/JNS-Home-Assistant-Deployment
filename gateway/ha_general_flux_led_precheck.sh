#!/usr/bin/env bash
set -Eeuo pipefail
echo '=== DNS RECORD DISCOVERY FOR 10.10.10.170 ==='
ssh -o BatchMode=yes -o ConnectTimeout=10 nodeb 'bash -s' <<'NODEB'
set -Eeuo pipefail
for dns in 10.10.10.247 10.10.10.248; do
  echo "--- DNS $dns AXFR home.arpa ---"
  if command -v dig >/dev/null; then
    dig +time=2 +tries=1 AXFR home.arpa @"$dns" 2>/dev/null | grep -F '10.10.10.170' || true
  fi
done

echo '--- Try SSH/read-only config discovery on DNS hosts ---'
for host in 10.10.10.247 10.10.10.248; do
  echo "HOST=$host"
  ssh -o BatchMode=yes -o ConnectTimeout=4 -o StrictHostKeyChecking=accept-new root@"$host" \
    "grep -RsnF '10.10.10.170' /opt/AdGuardHome /etc/AdGuardHome /var/lib/adguardhome /etc 2>/dev/null | head -20" 2>&1 || true
done
NODEB
