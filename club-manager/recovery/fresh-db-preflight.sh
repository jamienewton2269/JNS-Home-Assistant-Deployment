#!/usr/bin/env bash
# BSC Club Manager: non-destructive fresh database rebuild preflight.
# Never runs SQL or changes services. Run before any restore/installation.
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
printf 'BSC fresh database recovery preflight\n'
printf 'source=%s\n' "$ROOT"
for tool in bash python3 psql pg_dump pg_restore sha256sum; do
  if command -v "$tool" >/dev/null 2>&1; then
    printf 'tool_%s=present\n' "$tool"
  else
    printf 'tool_%s=missing\n' "$tool"
  fi
done
test -f "$ROOT/install-dev.sh" || { echo 'ERROR: baseline installer absent'; exit 2; }
test -f "$ROOT/migrations/002_backend_domains.sql" || { echo 'ERROR: migrations absent'; exit 2; }
test -f "$ROOT/migrations/022_local_beta_service_role.sql" || { echo 'ERROR: migration 022 absent'; exit 2; }
echo '=== migration files (inventory only; no automatic application) ==='
find "$ROOT/migrations" -maxdepth 1 -name '*.sql' -type f -print | LC_ALL=C sort
echo '=== source integrity manifest ==='
(cd "$ROOT" && find migrations auth beta handover -type f -print0 | LC_ALL=C sort -z | xargs -0 -r sha256sum)
echo '=== safety checks ==='
echo 'fresh DB: schema bootstrap, migration order, roles and functions require disposable PostgreSQL acceptance'
echo 'restore: real member records require a separate encrypted verified backup'
echo 'secrets: signing keys, passkey relying-party settings, TLS keys and service credentials are not in Git'
echo 'access: no live CT101/Joomla changes; two-officer approval and MFA are production requirements'
echo 'STOP: no database or system changes made'
