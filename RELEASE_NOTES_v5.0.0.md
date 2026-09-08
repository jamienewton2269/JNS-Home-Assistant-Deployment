# JNS Home Assistant Deployment Platform v5.0.0

Production security baseline.

- Mandatory Ed25519 publisher signatures for all deployment packages.
- Public-key trust store with separate `config` and `platform` scopes.
- Unsigned legacy package installation disabled.
- Signed platform updater with full integration-tree backup and restart confirmation.
- Tamper-evident hash-chained audit trail; new installs block if audit integrity fails.
- Process-local and Linux filesystem operation locks.
- Durable atomic writes and fsync-backed transaction records.
- Disk-space reserve checks before mutation.
- Suspicious package quarantine.
- Stable out-of-tree emergency recovery utility.
- Automatic Home Assistant configuration validation and rollback.
- Interrupted transaction recovery, backup hash verification and rollback drift protection.
- Offline key generation, trust-store and package signing tools.
