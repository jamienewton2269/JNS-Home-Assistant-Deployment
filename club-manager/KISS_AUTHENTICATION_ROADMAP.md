# Club Manager — KISS authentication and API integration

**Status: Development only. No public authentication endpoint is enabled. Synthetic data only.**

## Reuse rather than reinvent
- **WebAuthn:** upstream `webauthn==3.0.1` (Duo Labs `py_webauthn`) handles FIDO2 CBOR, signatures, RP ID/origin, challenge and required user verification. Do **not** implement custom cryptographic signature parsing.
- **TOTP fallback:** existing small RFC 6238 standard-library implementation in `auth/totp.py`; authenticated server must atomically consume verified counters using migration 016.
- **PostgreSQL:** only store for accounts, credentials, challenges, sessions, approvals, permissions, audit and business records; no Redis, etcd or identity-platform deployment.
- **Existing CT101 Python service:** one application, localhost-only in development, no public listening address. Existing `clubmgr` Basic authentication remains locked for sensitive reads and writes.
- **Existing GitHub runner Node C:** trusted single deployment route to Node A then CT101. No DNS/DHCP changes.

## Verified building blocks

| Part | Evidence | Scope |
|---|---|---|
| Officer API/session DB gates (017) | GitHub Actions run 42366548051 | Role-restricted PostgreSQL functions; no HTTP session issuance |
| WebAuthn tests | Run 42366764554 | Upstream ceremony invoked; mocked credentials for synthetic unit tests |
| Credential/challenge storage (018) | Run 42366797107 | One-use challenge, counter and revoked-account checks |
| DB-backed ceremony bridge (019) | Run 42367332720 | Nonce retrieval, anti-replay and denied enrolment verified |
| TOTP fallback (016) | Run 42365735731 | Atomic code counter with disabled/suspended/revoked checks |

## Hard security requirements before connecting real officer screens
1. Configure exact secure HTTPS origin and RP ID on a private dev test hostname; no claim that `localhost` may safely serve passkey flows in production.
2. Establish independently approved initial **synthetic** administrator enrolment and account binding. Current registration intentionally requires two approved, currently MFA-authenticated recovery officers; first-officer bootstrap is **not enabled**.
3. Install pinned upstream WebAuthn library in isolated app environment and provide an authenticated, least-privilege verification service account. NOLOGIN PostgreSQL roles do not themselves permit connections.
4. Build a tiny HTTP ceremony interface in the existing service with request limits, strict origin/CSRF handling, rate limiting, secure HttpOnly/SameSite cookies and server-side session validation. WebAuthn finish must verify the signature, expected challenge, origin, RP ID and user verification before an MFA session can be issued.
5. TOTP secrets require encrypted storage and secure enrolment. Do not place secrets in current PostgreSQL registry or logging.
6. Connect **read-only** screen APIs first, mapping permissions for each screen and testing cross-officer access, expiration and revocation. Writes and approvals remain independently gated.
7. Add real cryptographic WebAuthn end-to-end tests using an upstream virtual authenticator/test fixture; current unit tests mock the crypto verifier and are **not proof of real device interoperability**.
8. Implement audit independence, named admin access, privileged maintenance approvals and formal release assessment before real data.

**Design guardrail:** no public master database, no new external service, no real members, no live payments, no unlock of shared-password admin views.
