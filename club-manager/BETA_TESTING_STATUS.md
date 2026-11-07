# Club Manager — beta entrance and release gates

As of 2026-11-07: **UX beta available with synthetic static data**. **Authenticated CT101 operational beta remains blocked until explicitly verified.** Production release gate remains closed.

## Tracks

### A. User-interface UX beta (available now)

Download the self-contained ZIP from the conversation attachment (`club_manager_synthetic_beta_0_1.zip`), extract and open `index.html` on a desktop or phone. Use `beta-test.html` for eight exercises and local JSON feedback export.

- Seven navigable preview sections; member-name search; mobile-responsive layout.
- All figures/names synthetic and offline; no database connection, real account login, payments, Joomla updates or production data.
- A design review is **not** proof of a secured operational workflow.

### B. CT101 read-only operational beta (not enabled yet)

Implemented database-side:
- `017`: named, short-lived MFA session and permission-bound member/dashboard reads
- `018–019`: upstream WebAuthn library, credential store, nonce replay guard, PostgreSQL-backed ceremony bridge; unapproved enrolment denied
- `020`: five read-only, permission-specific projections for moorings, clubhouse, renewals, committee and security
- `021`: credential-bound MFA/API session issuance and logout revocation restricted to the isolated NOLOGIN authn service role
- `beta/read_api.py` and `beta/officer_controller.py`: fixed route-to-SQL adapter and upstream WebAuthn-to-secure-cookie integration, **not attached to an HTTP listener**.

No new services, identity platforms, brokers or databases.

## Blockers before operational beta

- [ ] Secure private HTTPS browser origin and exact WebAuthn RP ID confirmed, with explicit approval for any access/network changes.
- [ ] Independently authorised one-time **first synthetic officer** bootstrap: no self-registration and no two-officer recovery bypass. Retire bootstrap once complete.
- [ ] Verified, individual authenticated account binding; real WebAuthn authenticator challenge/response through HTTPS; user verification and crypto signature validated end-to-end (unit tests mocking signatures are not sufficient).
- [ ] Isolated, named PostgreSQL service roles with NOLOGIN grant inheritance; no elevation of legacy `clubmgr` role.
- [ ] Session cookie is Secure/HttpOnly/SameSite=Strict; CSRF/origin checks and login throttling; server-side access revocation tested.
- [ ] Wire read-only API in existing Python app. Confirm individual dashboard permissions and no sensitive overexposure.
- [ ] Execute full synthetic CT101 acceptance matrix with negative cases and rollback-only data fixtures.
- [ ] No exposed payment or mutation endpoints; record the named reviewer and release version.
- [ ] Complete a usable private-browser workflow with an approved beta tester; record signoff.

## Additional production gates

Independent audit, UK GDPR work, operational backup restore, Joomla sync safety, verified payment adapters/reconciliation, formal independent security assessment and club authorisation remain mandatory.

**Never introduce real member or committee personal information until production-release approval.**
