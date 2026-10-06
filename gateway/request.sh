#!/usr/bin/env bash
set -euo pipefail
ssh nodeb 'curl -fsS -X POST -H "Content-Type: application/json" --data "{\"text\":\"turn on the garden waterfeature from 9am until bedtime\"}" http://127.0.0.1:8099/api/analyse-start'
