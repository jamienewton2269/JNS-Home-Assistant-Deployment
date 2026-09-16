# JNS Home Assistant Deployment Platform v5.4.1

## HACS-first bootstrap

This release makes the production bootstrap path the development path. HACS installs/updates `jns_deployment`; the integration then registers this same GitHub repository with Home Assistant Supervisor and provisions the first-party **JNS Secure SFTP** app.

### Transport
- Standard OpenSSH `internal-sftp` transport.
- Deployment-only `jnstransfer` account.
- Strong password authentication is the default; authorized keys remain optional at app level.
- SFTP-only chroot to `/config/jns/sftp/incoming`; no shell or forwarding.
- Port 2222 by default.
- Transport credentials do not replace Ed25519 package trust or SHA-256 integrity checks.

### Operations
The platform keeps transactional install/update/repair/uninstall/rollback behavior from v5.1.2. The Windows Management Console v5.4 uses the SFTP inbox as the transport and exposes Deploy, Update, Repair and Uninstall as first-class actions.

### Upgrade
Existing HACS installs update normally. After restarting Home Assistant, open **Settings → Devices & services → JNS Home Assistant Deployment Platform → Configure** and set a unique SFTP password of at least 24 characters. JNS will provision or repair the companion app.
