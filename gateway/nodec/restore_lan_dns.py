#!/usr/bin/env python3
"""Update only Node C resolv.conf through verified root SSH; auto rollback on failure."""
import subprocess, shlex
host = ["ssh","-T","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes",
        "-o","ConnectTimeout=6","root@10.10.110.13"]
remote = r'''set -euo pipefail
test "$(hostname -s)" = nodec
test "$(readlink -f /etc/resolv.conf)" = /etc/resolv.conf
test -f /etc/resolv.conf
before=$(mktemp /etc/resolv.conf.pre-jns-lan-dns-XXXXXXXX.bak)
cp -p /etc/resolv.conf "$before"
tmp=$(mktemp /etc/resolv.conf.jns-stage-XXXXXX)
cat > "$tmp" <<'EOF'
search home.arpa
nameserver 10.10.110.248
nameserver 10.10.110.249
EOF
chmod --reference=/etc/resolv.conf "$tmp"
chown --reference=/etc/resolv.conf "$tmp"
restore() {
 if [ "$?" -ne 0 ]; then
   cp -p "$before" /etc/resolv.conf
   echo "VALIDATION_FAILED_DNS_ROLLED_BACK"
 fi
}
trap restore EXIT
mv "$tmp" /etc/resolv.conf
grep -qx 'nameserver 10.10.110.248' /etc/resolv.conf
grep -qx 'nameserver 10.10.110.249' /etc/resolv.conf
getent ahostsv4 nodeb.home.arpa | grep -q '10.10.110.12'
getent ahostsv4 ha-general.home.arpa | grep -q '10.10.110.223'
getent ahostsv4 github.com >/dev/null
echo "DNS_CHANGE_SUCCESS"
echo "RESOLVERS"
grep -E '^(search|nameserver)' /etc/resolv.conf
echo "DNS_RESOLUTION"
getent ahostsv4 nodeb.home.arpa | head -1
getent ahostsv4 ha-general.home.arpa | head -1
echo "EXTERNAL_OK"
'''
proc=subprocess.run(host+[shlex.quote("bash")+" -c "+shlex.quote(remote)],
                    capture_output=True,text=True,timeout=50)
print(proc.stdout[-2400:])
if proc.returncode:
    print("DNS_CHANGE_FAILED",proc.stderr[-450:])
    raise SystemExit(1)
