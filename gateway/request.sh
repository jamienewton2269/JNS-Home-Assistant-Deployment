#!/usr/bin/env bash
set -uo pipefail
echo "=== READ-ONLY PJ2101A DHCP / DNS DISCOVERY ==="
date -u -Is
echo "reference old IP: 10.10.10.177 (NOT assumed current)"
for host in local nodeb nodea; do
  echo "--- HOST $host ---"
  if [ "$host" = local ]; then
    cmd='bash -s'
  else
    cmd="ssh -o BatchMode=yes -o ConnectTimeout=6 $host bash -s"
  fi
  $cmd <<'HOSTSCRIPT' || echo "HOST UNAVAILABLE"
set +e
hostname
for ct in 247 248; do
  if ! pct status "$ct" 2>/dev/null | grep -q running; then continue; fi
  echo "=== DHCP CT$ct ==="
  pct exec "$ct" -- sh -c '
    echo "LEASE FILES"
    find /var/lib /run -type f \( -name "*lease*" -o -name "*dnsmasq*" \) 2>/dev/null | head -30
    echo "RELEVANT LEASES"
    find /var/lib /run -type f -name "*leases*" 2>/dev/null |
      while read f; do grep -Eih "pj2101|tuya|meter|smart|10\.10\.10\.177" "$f" 2>/dev/null | head -50; done
    echo "RELEVANT RESERVATIONS"
    grep -RihE "pj2101|tuya|meter|smart|10\.10\.10\.177" /etc/dnsmasq.conf /etc/dnsmasq.d /etc/hosts 2>/dev/null | head -60
    echo "LEASE COUNTS"
    find /var/lib /run -type f -name "*leases*" 2>/dev/null |
      while read f; do wc -l "$f"; done
  ' 2>&1 | head -170
done
HOSTSCRIPT
done
echo "=== END READ-ONLY DHCP DISCOVERY ==="
