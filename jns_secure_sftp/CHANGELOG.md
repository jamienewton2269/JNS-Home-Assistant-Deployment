# Changelog

## 0.4.1

- Fixes public-key-only startup when exactly one management-PC SSH key is configured.
- Uses a newline-safe bashio list read pattern so the final authorized key is never dropped.
- Logs only the configured public-key count; key contents and private credentials are never logged.

## 0.4.0

- Adds v5.5 per-management-PC enrollment support.
- Exports the persistent Ed25519 server **public** host key for verified fingerprint pinning.
- Supports key-only operation with one authorized key per enrolled management PC.
- Legacy password mode remains available only for migration/recovery.
- No shell, forwarding, tunnel or root-login capability is added.

## 0.3.x

- First-party standards-based JNS Secure SFTP transport.
- OpenSSH `internal-sftp`, persistent host keys, isolated `/incoming` chroot.
- Added authorized-key support while retaining legacy password migration compatibility.
