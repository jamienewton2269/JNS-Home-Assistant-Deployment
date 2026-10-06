#!/usr/bin/env bash
set -uo pipefail
echo "=== CT130 MONITOR READ-ONLY CHECK ==="
date -Is
timeout 20 ssh -o BatchMode=yes -o ConnectTimeout=5 nodeb 'set -e; echo "host=$(hostname)"; pct status 130; pct exec 130 -- systemctl is-active jns-netmon.service; echo "health:"; pct exec 130 -- curl --noproxy "*" -fsS --max-time 5 http://127.0.0.1:8080/health; echo; echo "api:"; pct exec 130 -- curl --noproxy "*" -fsS --max-time 35 http://127.0.0.1:8080/api/state | python3 -c '\''import json,sys; d=json.load(sys.stdin); print("version:",d.get("version")); print("devices:",len(d.get("devices",[]))); print("links:",len(d.get("links",[])))'\'''
