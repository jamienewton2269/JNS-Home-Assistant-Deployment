#!/usr/bin/env bash
set -u
echo "=== JNS EXISTING ACCESS / DEPLOYMENT PATH AUDIT (READ ONLY) ==="
date -Is; hostname
for p in /usr/local/sbin/jns-gateway-exec /usr/local/libexec/jns-gateway-ha-network-identity-install /usr/local/libexec /opt/jns-ha-control-plane; do
 if [[ -e "$p" ]]; then ls -ld "$p"; else echo "Missing: $p"; fi
done
echo "=== Trusted gateway routes (names only; NO script contents) ==="
if [[ -f /usr/local/sbin/jns-gateway-exec ]]; then
 grep -Eo '[a-z][a-z0-9_-]+\)' /usr/local/sbin/jns-gateway-exec | sort -u | head -80 || :
fi
echo "=== Proxmox hosts available in local API ==="
if command -v pvesh >/dev/null; then
 pvesh get /nodes --output-format json 2>/dev/null | python3 -c 'import json,sys; print("\n".join(str(x.get("node"))+" "+str(x.get("status")) for x in json.load(sys.stdin)))' || :
fi
echo "=== Existing ssh key metadata (filenames ONLY) ==="
for d in /root/.ssh /home/github-runner/.ssh; do
 if [[ -d "$d" ]]; then find "$d" -maxdepth 1 -type f -printf '%f\n' | grep -Ev '^known_hosts' || :; fi
done
echo "=== Node B authentication test, existing keys only ==="
timeout 9 ssh -o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=yes root@10.10.10.235 'printf "NODE_B_OK "; hostname' 2>&1 || :
echo "Done. No new tokens/keys created, no state changes."
