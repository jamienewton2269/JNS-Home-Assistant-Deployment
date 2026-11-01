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
