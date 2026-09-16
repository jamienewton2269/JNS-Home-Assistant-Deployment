# JNS Home Assistant Deployment Platform v5.4.1

HACS-installed, signed-package deployment and lifecycle management for Home Assistant.

## Production bootstrap

1. Add this repository to HACS as a custom **Integration** repository and install **JNS Home Assistant Deployment Platform**.
2. Restart Home Assistant.
3. Add/configure the JNS integration in **Settings → Devices & services** and enter a unique deployment-only SFTP password (minimum 24 characters).
4. On Home Assistant OS/Supervisor, JNS registers this same repository as an App repository, installs **JNS Secure SFTP**, configures it as SFTP-only on host port `2222`, and starts it.
5. Configure the JNS Windows Management Console with the Home Assistant host, port `2222`, user `jnstransfer`, and the same password.
6. Use **Deploy / Update / Repair / Uninstall**. Package signatures, hashes, path policy, configuration checks and transactions remain authoritative.

## Security model

SFTP is deliberately only the encrypted delivery channel. A file arriving in `/config/jns/sftp/incoming` is not trusted merely because SFTP accepted it. Deployable packages require the JNS format-3 Ed25519 signature and SHA-256 integrity records, a trusted publisher/scope, permitted destinations and the deployment transaction checks.

JNS Secure SFTP provides no interactive shell, forwarding, tunnels or root login. The SFTP account is chrooted to the deployment inbox. Keep TCP 2222 restricted to the management LAN/VPN.

## Existing installations

HACS upgrades the integration code. Existing config entries are migrated without disabling the deployment executor. If the SFTP password has not yet been configured, JNS posts a Home Assistant notification and the integration **Configure** flow provisions the companion app.

See `RELEASE_NOTES_v5.4.1.md`, `SECURITY.md`, and `PRODUCTION_UPGRADE.md` for more detail.
