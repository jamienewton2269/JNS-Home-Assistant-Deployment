# JNS v5.0.0 Production Acceptance

Do not enable unattended production deployment until all gates pass on the target system.

## Repository gates
- Hassfest green.
- HACS validation green.
- static verifier green.
- production security self-test green.

## Trust gates
- private signing key remains off Home Assistant.
- public-key fingerprint recorded independently.
- `publishers.json` copied to `/config/jns/trust/`.
- `list_trusted_publishers` reports expected ids/scopes/fingerprints.

## Live package gates
- valid signed package validates and dry-runs.
- unknown publisher rejected.
- invalid signature rejected.
- payload hash mismatch rejected.
- unsigned v4 package rejected.
- live install succeeds and HA config check passes.
- rollback restores original state.

## Security gates
- traversal, undeclared files, symlinks/special files, duplicate targets and ZIP compression abuse are rejected.
- config-only publisher cannot install a platform update.
- audit log verifies; deliberate audit tamper is detected in a disposable test environment.
- new install is blocked while audit is corrupt.
- rollback drift protection rejects a changed live target unless force is explicitly used.

## Recovery gates
- simulated interrupted transaction is detected and recoverable.
- standalone emergency recovery can restore a disposable platform-update backup.

## Operations
- independent Home Assistant backups/snapshots are enabled.
- emergency SSH/SFTP access is documented.
- the deployed version is preserved as a tagged Git release.
