#!/usr/bin/env bash
set -Eeuo pipefail
echo "QUEUE_SELFTEST_OK"
echo "host=$(hostname)"
echo "time=$(date -Is)"
test -d gateway/queue
test -d gateway/results
test -d gateway/status
