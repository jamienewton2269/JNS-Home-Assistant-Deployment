# SAGE runner recovery — evidence and safe remediation

## Observed 2026-11-15 (gateway/sage-result.txt on main)
- Runner is `NT AUTHORITY\\NETWORK SERVICE`.
- Westminster source exists at `C:\\src\\JNS-WESTMINSTER-CHIMES\\WestminsterSkill`, owned by `SAGE\\jnewt`.
- Git refused to operate on the source with exit 128 (`dubious ownership`).
- `ask` CLI was not on PATH; access to the interactive user's npm/ASK profile paths was denied.
- `git`, `python`, and `npm` are available.
- This is **not** evidence that ASK credentials are absent or that the Alexa skill cannot deploy.

## Remediation (do not apply automatically to live runner)
1. Create a dedicated service-owned checkout under an authorised SAGE runner workspace, using a least-privilege service identity and repository-scoped credentials. Keep the interactive user's checkout untouched.
2. Use `git -C <service-owned-checkout> status --porcelain` and `git rev-parse HEAD` to validate ownership and checkout. Do **not** configure `safe.directory=*` or globally trust all repositories.
3. Install or expose the ASK CLI in a service-accessible tool location and verify `ask --version` without printing secrets.
4. Provision ASK/Amazon authorization for the service identity via approved encrypted credentials or GitHub Actions secrets. Never copy the interactive user's credential store into a public repository.
5. Run `ask` read-only account/skill preflight first, with sensitive output redacted and retained privately. Deploy only after explicit release approval.
6. If a dedicated service-owned workspace cannot be created, a **temporary read-only** diagnostic can use `git -c safe.directory=C:/src/JNS-WESTMINSTER-CHIMES/WestminsterSkill -C C:/src/JNS-WESTMINSTER-CHIMES/WestminsterSkill status --porcelain`; this is not a deployment fix and does not grant filesystem permissions.
7. Repeat a similar service-identity and workspace audit on Node C before altering its runner.

## Acceptance
- Runner can read its own service-owned checkout; Git returns 0.
- ASK CLI is found in runner's environment.
- ASK authorization succeeds under runner identity without user-profile access.
- Offline tests pass; production Alexa skill remains unchanged until approved.
