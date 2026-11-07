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


## 2026-11-07 private beta staging update

**Status: CT101 service staged and tested internally; private browser beta NOT YET RELEASED to testers.**

- Existing DNS already resolves `club-manager-dev.home.arpa`; no DNS/DHCP changes were made.
- `/opt/jns-club-beta` contains the same existing Python/PostgreSQL codebase with pinned upstream `webauthn==3.0.1`.
- `clubbeta` has a separate peer-authenticated local PostgreSQL login and only the isolated authn/API function grants. Legacy `clubmgr` was not elevated.
- Private `jns-club-manager-beta.service` is **disabled**, binding to `127.0.0.1:8766` only during internal tests. The existing `127.0.0.1:8765` service remains healthy.
- HTTP login/options/completion, secure cookie, logout, read-only screen routes and responsive cards/tables are staged. All sensitive content is permission checked in PostgreSQL on each request.
- CI tested HTTP host/origin checks, anonymous rejection, denied mutation methods, and per-officer passkey rate limiting. Workflow evidence: https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/42375467184
- Full CT101 private staging deployment and HTTP health tests: https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment/actions/runs/42375452242
- **Release blockers:** approved private HTTPS listener/certificate trust for beta browsers, verified two-person first-officer commissioning (the current recovery-only enrolment gate cannot bootstrap the first two officers), real physical/virtual authenticator browser test, active session evidence, and formal independent beta acceptance. Until then, the service remains disabled.
- No public endpoint, live membership data, real committee identities, payment processor, Joomla integration, DNS/DHCP modification or SSH tunnel was introduced.

Activation must be a separate authorised change, with a private TLS path and a supervised enrolment plan. Do not enable the systemd unit merely because the staging smoke tests pass.
