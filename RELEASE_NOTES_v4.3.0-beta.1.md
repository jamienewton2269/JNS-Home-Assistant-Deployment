# JNS Home Assistant Deployment Platform v4.3.0-beta.1

First beta test release.

## Added

- Inbox package discovery and validation status.
- Deployment planning (create / replace / unchanged / blocked).
- Installed-package inventory based on active committed transactions.
- Platform status action.
- Home Assistant diagnostics support.
- Automatic Home Assistant configuration validation after package installation.
- Automatic rollback if Home Assistant configuration validation fails.
- Interrupted transaction detection and explicit recovery.
- Format-2 trusted-hash JNS platform self-update.
- Complete integration-tree backup/replacement for platform updates.
- Pending/confirmed platform-update state across restart.
- Platform rollback.
- Integration Python syntax validation before platform update commit.
- Skip identical target files rather than rewriting them.
- Expanded beta self-tests and GitHub CI.

## Retained hardening

- SHA-256 per-file validation.
- undeclared-file rejection.
- traversal and special-file rejection.
- target/extension allow-list.
- ZIP size/compression-ratio limits.
- transaction backup hashes.
- rollback drift protection.
- single-operation lock.

## Upgrade note

v4.2.4 intentionally blocks ordinary packages from writing `custom_components/`.
Therefore the one transition to v4.3.0-beta.1 must be installed via HACS after the
beta repository is pushed. Future beta updates can use the new platform-update path.
