# JNS Home Assistant Deployment Platform v4.2.0 — Test Baseline

Initial HACS-testable repository baseline.

Included:
- Home Assistant config-flow integration.
- HACS repository metadata.
- Local transactional deployment executor.
- Package manifest validation.
- Per-file SHA-256 verification.
- ZIP path traversal protection.
- Symlink rejection.
- Undeclared-file rejection.
- Target-root allow-list.
- Staging before commit.
- Backup and transaction metadata.
- Manual transaction rollback.
- No deployment-package command execution.
- Example signed-by-hash deployment package.

This build is intended for controlled test environments before live Home Assistant use.
