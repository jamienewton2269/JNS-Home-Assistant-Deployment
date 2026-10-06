#!/usr/bin/env bash
set -uo pipefail
echo "=== NODE C HOST ACCESS CHECK ==="
date -Is
echo "runner=$(hostname) user=$(whoami)"
for host in nodea nodeb; do
  echo "-- $host --"
  timeout 8 ssh -o BatchMode=yes -o ConnectTimeout=4 "$host" 'printf "remote="; hostname; id; command -v pct || true; sudo -n -l 2>&1 | head -5' 2>&1 || true
done
