# JNS Deployment Platform v5.1.2

- Uses `jns/sftp/incoming` as the signed-package inbox for direct mapping from the first-party SFTP-only Home Assistant App.
- Migrates legacy package ZIPs from `jns/inbox` on startup.
- Adds deterministic nanosecond package transaction ordering, with mtime fallback for older records, preventing same-second install/repair/uninstall records from being processed out of order.
- Retains v5.1.1 `integration_package` validation and transactional install/update/repair/uninstall support.
