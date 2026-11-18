# BSC Club Manager integrated test release gate

**State: BLOCKED — do not deploy as an integrated release.**

## Verified source baselines

- Backend / advanced beta: `club-manager/` in `jamienewton2269/JNS-Home-Assistant-Deployment`, recovered in commit `eecb553c51899948d26b3823b5620341322ccb21`.
- Joomla bridge: Node C `/opt/bsc-joomla-membership`, clean `master` at `90fd97240b7045d946e32af04fe56357d465ef69`; read-only inventory run `44315512321`.
- The intended `bsc/joomla-bridge-review` branch was **absent** at the 2026-11-18 check. Its absence is a release blocker, not evidence of a successful merge.
- CT101 running service and database schema have not been reconciled against the recovered source.
- The dedicated repository `jamienewton2269/-BSC-Club-Manager` has not been verified as a full source mirror.

## Architecture contract

1. The authoritative PostgreSQL database must listen only on a Unix domain socket or an explicitly approved loopback/local interface. No internet-routable PostgreSQL port, public database credentials or reverse-proxied SQL.
2. The officer administrative application is private and must use authenticated TLS access through the approved internal ingress; no public administrative listener.
3. Krystal Joomla V3 is the *isolated online test member portal*. Public Joomla pages must not inherit member permissions. Signed member snapshots are outbound-only and contain an allowlisted minimum of member information. Member edits are requests, never direct database writes.
4. RaceDay Manager, YBM and other applications receive only explicitly approved reference records, with separate scoped read-only credentials and no authority over membership or finance.
5. Snapshot ingestion must verify Ed25519 signature, canonical payload digest, monotonic sequence and freshness; publish atomically, reject replay/tampering, retain last verified copy, and support key rotation/revocation.
6. Security evidence must include independent, access-controlled append-only authentication and mutation audit events, request correlation IDs, retention policy, clock synchronisation, backup and restore tests. Do not log secrets or raw member details.
7. Test with synthetic records until privacy, authorization, recovery and incident response checks pass. Never copy live member records to GitHub Actions or public CI artifacts.

## Blocking checks for a reproducible VM test release

- [ ] Import the full tracked Node C Joomla bridge into a review branch without secrets; inspect diff and preserve its provenance.
- [ ] Merge into a single source tree and run Python + PHP suites, including disposable MySQL tests.
- [ ] Compare actual CT101 PostgreSQL schema, roles, migrations, listener addresses and deployed service versions with the source.
- [ ] Produce an idempotent test installer and rollback plan with a dry-run migration report.
- [ ] Verify Unix socket/local-only PostgreSQL, application firewall, no public administrative listener and authenticated private ingress.
- [ ] Run synthetic member journeys against Joomla V3, including anonymous denial, self/household access, CSRF, revocation and officer approval.
- [ ] Verify signed outbound synchronisation, replay rejection, recipient-scoped reference data and complete rebuild of the disposable replica.
- [ ] Verify append-only independent audit collection, encrypted backup and restore, and no secrets in logs.
- [ ] Capture installation receipt with source SHA, schema version, test counts and network exposure scan.

## Deployment rule

No automatic changes to CT101, Joomla V2, live Joomla, or Krystal V3 until all blockers have evidence and a separate test target has been confirmed. The review/import workflow is **not** a deployment.
