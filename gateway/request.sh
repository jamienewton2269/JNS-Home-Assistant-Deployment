#!/usr/bin/env bash
set -euo pipefail

echo "NODE C:"
hostname
whoami
uname -a

echo
echo "SSH reachability:"
for host in 10.10.10.225 10.10.10.235; do
  printf "%s: " "$host"
  if timeout 3 bash -c "</dev/tcp/$host/22" 2>/dev/null; then
    echo "port 22 open"
  else
    echo "port 22 unavailable"
  fi
done
