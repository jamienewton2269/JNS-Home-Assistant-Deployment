#!/usr/bin/env bash
set -Eeuo pipefail
JOB="${1:?job json required}"
REAL="$(readlink -f -- "$JOB")"
python3 - "$REAL" <<'PY'
import json,sys
d=json.load(open(sys.argv[1],encoding="utf-8"))
assert d.get("job_type")=="dns_reservation_importer_install"
assert d.get("target")=="node-c"
PY
REPO_ROOT="$(cd "$(dirname "$REAL")/../.." && pwd)"
export JNS_REPO_ROOT="$REPO_ROOT"
exec /usr/local/libexec/jns-dns-reservation-importer-install
