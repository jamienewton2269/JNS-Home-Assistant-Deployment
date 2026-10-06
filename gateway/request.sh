#!/usr/bin/env bash
set -uo pipefail
echo "=== CT130 CLUSTER LOCATION CHECK ==="
date -Is
timeout 15 ssh -o BatchMode=yes -o ConnectTimeout=5 nodea 'pvesh get /cluster/resources --type vm --output-format json | python3 -c '\''import json,sys; xs=json.load(sys.stdin); ms=[x for x in xs if str(x.get("vmid"))=="130"]; print("CT130:", [(x.get("node"),x.get("status"),x.get("type")) for x in ms] if ms else "not found")'\'''
