#!/usr/bin/env bash
set -Eeuo pipefail
JOB="${1:?job json required}"
python3 - "$JOB" <<'PY'
import json,sys
d=json.load(open(sys.argv[1],encoding="utf-8"))
assert d.get("job_type")=="dns_reservation_importer_install"
assert d.get("target")=="node-c"
PY
exec /usr/local/libexec/jns-dns-reservation-importer-install
