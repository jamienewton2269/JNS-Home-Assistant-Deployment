# Veyra local account vault — specification (2026-10-19)

Status: approved direction, NOT implemented.

- Provide Settings > Accounts & Credentials. Local encrypted vault, under JNS control; per-provider login identity binding and manual selection of a saved identity; multiple profiles supported.
- Turn off Chrome's native password-save prompts and password manager/autofill where technically supported, without interfering with normal provider login or authenticated browser sessions. Chrome flags/policies must be validated against vendored Chrome before shipping.
- First use: user explicitly opts in to storing a password or enters it in Veyra vault. No hidden interception or unsolicited capture of password fields; saving enabled per identity and provider. User can view, edit, revoke and delete saved credentials; mask by default and require local confirmation before reveal.
- Reuse email across provider sites; never infer that identical emails imply identical passwords. Sharing a secret across sites requires explicit per-provider opt in, and binding to an approved exact hostname/origin. Block phishing lookalikes; avoid URL suffix checks.
- Autofill through trusted extension logic limited to explicit approved provider origins and real login elements, after user opt-in. Do not leak secrets to unauthorised origins, third-party frames or arbitrary injected scripts. Avoid sending secrets via command-line, log files, query strings, telemetry and crash reporting.
- Encryption at rest using OS/keyring or cryptographic vault with separate unlock secret; simple filesystem permissions alone insufficient. Decide how headless boot unlock works; do not put a decryption key beside ciphertext in freely readable plaintext. Prefer encrypted backup and recovery. Consider local PIN vs durable encryption key carefully.
- Provider cookies remain in provider-specific browser profiles; watch history local and separate from vault. Vault backup requires encrypted export, never raw upload to GitHub.
- Tests: multi-provider login, same email/different passwords, manual revoke, phishing origin rejection, logout/relogin, reboot persistence, browser privacy prompts suppressed, offline behaviour, provider website changes.
- Do not alter currently working Cage/seatd/graphics baseline during vault work.
