# Fresh Club Manager database/server recovery — controlled build

Status: **preflight implemented; full automated rebuild and restore NOT yet acceptance-tested**.

## Source of truth

- Backend/beta: `club-manager/` in JNS-Home-Assistant-Deployment.
- Joomla bridge: Node C `/opt/bsc-joomla-membership`, commit `90fd97240b7045d946e32af04fe56357d465ef69`.
- Authoritative database: CT101 PostgreSQL. Its actual schema/data and recoverable backup have **not** been inspected.
- The dedicated private repository is not a verified replacement for either source.

## Rules to preserve

1. One PostgreSQL authority; Joomla V3 receives only signed, minimal outbound projections and never gets direct master DB access.
2. Default deny: separate PostgreSQL service roles, explicit grants, revoked PUBLIC EXECUTE; privileged maintenance requires designated operator, recent MFA and independent second approval. PostgreSQL superuser and host root remain out-of-band privileges requiring operational controls.
3. Named officer identities, WebAuthn preferred, TOTP fallback, server-side session revocation, no shared privileged passwords.
4. Membership history, households, subscriptions, payments, vessels, moorings and committee access preserved by the complete schema and migrations; do not reconstruct from an incomplete handwritten schema.
5. Independent tamper-evident audit export, encrypted backups, controlled key custody, privacy retention and documented restore exercise.
6. No genuine member data, secrets or database dumps in GitHub or diagnostic logs.

## Safe recovery sequence

1. Provision a **new disposable Debian guest** with a new hostname, no live DNS cutover, no public listener and no connectivity to Joomla production.
2. Checkout the exact backend source revision and separately preserve Node C bridge revision. Run `bash club-manager/recovery/fresh-db-preflight.sh`; retain its manifest as an installation receipt.
3. Inspect `club-manager/install-dev.sh` and stage its required `/tmp/jns-club-manager-app.py` from the matching reviewed source. The existing installer requires hostname `club-manager-dev` and is **not** a portable production installer.
4. Install the baseline schema in the disposable guest only. Review and execute migration files in **dependency order**, including both separately named `016` migrations. Do not blindly glob and apply them to a populated DB.
5. Validate schema objects, function grants, NOLOGIN service roles, audit protections, and the complete synthetic test matrix. Check that security-definer functions cannot be invoked by anonymous or legacy accounts.
6. Stage the beta server and read-only API; keep it loopback-only and disabled until HTTPS origin, WebAuthn RP ID, officer bootstrap and real browser acceptance are approved.
7. Package the Joomla bridge independently and run disposable PHP/MySQL signed-snapshot/import/portal tests before any V3 installation.
8. For **data restoration**, obtain an encrypted verified CT101 backup, restore it only into an isolated guest, verify row counts, integrity, grants, sequence state, schema versions and audit chain, then perform officer-reviewed cutover. Never treat synthetic fixtures as recovered records.
9. Verify encryption/signing key custody, backup rotation, recovery approvals, audit continuity and rollback before any production activation.

## Recovery acceptance checklist

- [ ] Clean disposable install from pinned source revisions
- [ ] All SQL migrations applied and recorded exactly once
- [ ] PostgreSQL grants and security tests pass
- [ ] Authn/API integration and real browser WebAuthn test pass
- [ ] PHP 8.4 and disposable MySQL/Joomla tests pass
- [ ] Signed snapshot and replay/rollback tests pass
- [ ] Encrypted backup restored with verified member counts and audit continuity
- [ ] Fresh guest can restart and recover without external hidden files
- [ ] Secrets restored through a separate protected channel
- [ ] Named two-officer approval and documented recovery receipt

**Do not claim full disaster recovery until all acceptance items are verified.**
