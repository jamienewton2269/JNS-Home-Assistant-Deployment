#!/usr/bin/env bash
set -uo pipefail
echo "=== NODE C ACCESS CHECK ==="
date -Is
timeout 20 ssh -o BatchMode=yes -o ConnectTimeout=5 nodea 'timeout 8 ssh -o BatchMode=yes -o ConnectTimeout=4 nodec '\''echo "host=$(hostname)"; pct status 130; pct exec 130 -- systemctl is-active jns-netmon.service; pct exec 130 -- curl --noproxy "*" -fsS --max-time 5 http://127.0.0.1:8080/health'\'''
