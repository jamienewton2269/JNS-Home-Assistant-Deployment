#!/usr/bin/env bash
set -u

echo "NODE C:"
hostname
whoami
uname -a

echo
echo "SSH authentication test:"
for host in 10.10.10.225 10.10.10.235; do
  echo "--- $host ---"
  ssh -o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=accept-new root@$host 'hostname; whoami; pveversion 2>/dev/null | head -1' || echo "SSH_AUTH_FAILED"
done
