#!/usr/bin/env bash
# JNS DNS/DHCP dual-stack preflight, read-only; run on Node C.
set -Eeuo pipefail
MASTER=/mnt/jns-dns-master/jns-dns
echo "=== JNS DNS/DHCP DUAL-STACK PREFLIGHT $(date -Is) ==="
echo "=== Current master release ==="
if [[ -r "$MASTER/current" ]]; then cat "$MASTER/current"; else echo "master current unavailable"; fi
echo "=== Registered DHCP source files ==="
if [[ -d "$MASTER/dynamic-dns" ]]; then
  find "$MASTER/dynamic-dns" -maxdepth 1 -type f -name '*.tsv' -printf '%f (%s bytes)\n' | sort
else echo "missing dynamic-dns"; fi
echo "=== CT249 (DNS-only) config ==="
pct exec 249 -- sh -c "grep -E '^(dhcp-range|dhcp-script|dhcp-leasefile|addn-hosts|conf-file|enable-ra|ra-param|server|local|domain)=' /etc/dnsmasq.conf || true"
echo "=== Node C DHCP/DNS containers ==="
pct list
echo "=== DHCP services bound to ports, Node C ==="
ss -lunp | grep -E '(:67|:547|:53)[[:space:]]' || true
echo "=== Current DNS A/AAAA records from both replicas ==="
for server in 10.10.110.247 10.10.110.248; do
  for name in ha-general.home.arpa jns-dns-nodea.home.arpa jns-dns-nodeb.home.arpa sage.home.arpa; do
    for type in A AAAA; do
      printf '%s %s %s: ' "$server" "$name" "$type"
      dig +short +time=2 +tries=1 @"$server" "$name" "$type" | paste -sd ',' -
    done
  done
done
echo "=== Router advertisements, without network changes ==="
if command -v rdisc6 >/dev/null; then timeout 8 rdisc6 -1 vmbr0 2>&1 | head -45 || true; fi
echo "=== IPv6 address and route ==="
ip -6 -brief address show dev vmbr0
ip -6 route show default
echo "=== Existing publisher code ==="
sed -n '1,85p' /opt/jns-deployment/jns-dns-kit/publish.sh
echo "=== PREFLIGHT COMPLETE - NO CHANGES MADE ==="
