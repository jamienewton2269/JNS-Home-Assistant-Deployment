# JNS Deployment Platform v5.5.7

## Safe management-PC enrollment during legacy SFTP migration

v5.5.7 fixes the live enrollment failure seen when the legacy JNS Secure Transfer Gateway still owns TCP 2222.

- Keeps the legacy gateway running during migration.
- Uses the first free JNS SFTP host port in 2222-2232 and returns that exact port to the Windows Manager.
- Persists the Supervisor-selected port in Home Assistant configuration instead of reverting to 2222.
- Treats the JNS management registry as the authority for SFTP public keys.
- Does not automatically adopt unknown keys left in JNS Secure SFTP by an interrupted or failed enrollment.
- Rolls back the SFTP key set, management registry, publisher trust and temporary HA system identity if enrollment fails.
- On restart, an installation with no enrolled management PCs clears/stops the new SFTP transport rather than retaining orphan keys.
- The legacy JNS Secure Transfer Gateway is not stopped or uninstalled by this patch; it remains available for rollback until the new PC is commissioned.

JNS Secure SFTP remains v0.4.3. Windows Management Console v5.5.2 remains protocol-compatible.
