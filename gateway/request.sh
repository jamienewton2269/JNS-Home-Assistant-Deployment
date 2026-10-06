#!/usr/bin/env bash
set -uo pipefail
echo "=== NODE C LOCAL ROOT ROUTE CHECK ==="
date -Is
timeout 8 ssh -o BatchMode=yes -o ConnectTimeout=4 -o StrictHostKeyChecking=no root@127.0.0.1 'hostname; id -u; pct status 130'
