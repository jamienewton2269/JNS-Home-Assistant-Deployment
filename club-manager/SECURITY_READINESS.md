# Club Manager — production security readiness register
Status: NOT READY FOR PRODUCTION — synthetic data only.
Evidence baseline: 2026-11-01.

## Verified technical controls
- CT101 localhost-only development service; Node C to Node A deploy path.
- PostgreSQL member-event append/revise integrity and hash-chain regression.
- Least-privilege database account and explicit PUBLIC EXECUTE revocation.
- Anonymous access denied; cross-origin/missing-origin writes rejected.
- App service and audit endpoint health verified by GitHub Actions.
- Rollback-only synthetic tests, no genuine member records.


## Confirmed security policy — 2026-11-03
- **MFA:** WebAuthn/passkeys or hardware security keys preferred; authenticator TOTP fallback.
- **Recovery:** two distinct independently MFA-authenticated authorised officers; neither the requester nor recovering account may approve.
- **Sensitive PostgreSQL maintenance:** designated administrators only; independently MFA-authenticated two-person approval required before a narrowly scoped maintenance broker executes authorised tasks.
- **Privileged sessions:** MFA assurance <=15 minutes; renewal required after expiry; revocation invalidates access.
- **Request approval windows:** maximum 24 hours; no cross-user reuse of MFA proof.
- **No general write/privileged read without MFA:** prototype shared-password sensitive paths locked; no live officer enrolment, credential verifier, session issuer or operational maintenance broker yet.
- **Database administrators:** PostgreSQL superusers/OS root inherently can bypass ordinary DB permissions and triggers. The policy is **not** enforced on direct superuser connections until a separate MFA-protected management access path, restricted superuser access, dual-control runbook and independent audit evidence are verified.
- **Development release gate:** synthetic identities only, no public/Joomla activation, no live payment processors.
- **Evidence:** CT101 migration 015 and synthetic gate run https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/41630552335 (passed).
- **Additional acceptance tests needed:** genuine WebAuthn challenge/origin/RP validation and signature counters; TOTP secret protection and replay rejection; phishing-resistant MFA where supported; lockout, recovery proofing, onboarding, device-loss drills, role revocation; independent persistent security-event audit; request expiration, concurrent approvals and external DBA access controls.


## MFA integration milestone — 2026-11-07 (development)
- Added isolated standard-library TOTP primitives in `club-manager/auth/club_mfa_core.py`: RFC 6238 SHA-1 six-digit authenticator codes, 30-second periods with one-step skew, constant-time comparisons, replay-step checks, cryptographically random secret generation and opaque session handles.
- Unit tests include RFC vector, replay rejection, invalid code rejection, time skew and fail-closed privileged session checks. GitHub Actions: https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/42365655216
- Staged the isolated Python module on CT101 under `/opt/jns-club-manager/auth-staging/`; **not connected to running HTTP application**.
- Migration `016_totp_replay_counter.sql` adds an atomic monotonic counter bound to an active named officer and enrolled/verified, unrevoked TOTP credential. It is callable only by `club_authz_service` NOLOGIN, not by prototype role. Rollback-only synthetic validation passed: https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/42365727704
- **Still blocking:** build and test WebAuthn RP/origin/challenge validation using a maintained library; secure TOTP secret encryption with keys outside PostgreSQL; trusted identity enrolment and MFA verification service; atomic session issuance; CSRF/HTTPS/browser cookies; login throttling and independently audited two-officer account recovery.
- **Do not conflate cryptographic primitives or a privileged counter function with verified MFA sign-in.** No real officer identities, app login endpoints, or database write permissions have been enabled.

## Mandatory release gates — all must pass before real data
1. **Identity and access:** replace one shared Basic Auth secret with individual named accounts, strong MFA for officers, RBAC per operation, secure sessions, revocation, and independent break-glass procedure. Include failed-login throttling.
2. **Audit independence:** replicate signed, sequenced audit events to independently administered append-only storage outside CT101; anchor and periodically verify digests; privileged-operator tampering must trigger an alert. A DB trigger alone is insufficient.
3. **Privacy / UK GDPR:** record controller/processor roles, lawful bases, retention, security measures, privacy notices, SAR identity verification, timed access/portability, justified deletion with backups lifecycle and lawful-exception handling, and a DPIA assessment/decision. Do not delete records required for statutory retention without review.
4. **Sync safety:** implement outbound-only, mutually authenticated, least-data Joomla projection; quarantine inbound member-submitted changes pending validation; signed/idempotent events, bounded retries and replay tests. Public host must never connect to private master DB.
5. **Payments:** implement authorised QuickBooks OAuth access, encrypted token storage, minimum scopes, webhook verification, reconciliation and recovery. Never store card numbers or pretend to be payment processor.
6. **Operational resilience:** encrypted tested off-site backups, full restore exercise, independently verified audit restore, patching and vulnerability scanning, capacity/retention monitoring, RPO/RTO and incident recovery exercises.
7. **Incident response:** alerting, credential compromise isolation, bulk-extraction thresholds and lockdown with protected operator access, evidence preservation, documented UK GDPR personal-data breach assessment and regulator notification decisions.
8. **Assurance:** documented architecture/threat model, OWASP ASVS 5.0 test matrix and findings, dependency SBOM/license review, DAST/SAST, independent penetration testing, remediation and retest.
9. **Governance:** two-person approvals enforced on the operation itself (not just a table check), least-privilege access recertification, safeguarding considerations for junior-member data and club committee release sign-off.
10. **Go-live isolation:** production host separated from development and home automation; TLS end-to-end, access policy, DNS/firewall review with specific approval, synthetic test data purge, release rollback plan, production secrets in protected storage.

## Do not mistake these for completed capabilities
- A database table is not a deployed GDPR workflow.
- A CHECK constraint is not dual-control authorisation.
- A local SHA-256 chain is not independently immutable evidence.
- A localhost prototype with Basic Auth is not a deployable member-facing product.
- A successful CI run is not third-party certification or Cyber Essentials certification.

## Evidence and acceptance
- Security hardening: GitHub Actions run 41344480380.
- Backend integrity regression: GitHub Actions run 41343804165.
- Backend schema migration: GitHub Actions run 41343643064.
Release decision: BLOCKED pending mandatory gates, full evidence package, and authorised independent assessment.
