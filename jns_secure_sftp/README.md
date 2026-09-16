# JNS Secure SFTP 0.3.1

A deliberately small Home Assistant App used only to transport JNS deployment packages.

## Security boundary

- OpenSSH `internal-sftp` only; no interactive shell.
- Dedicated non-root `jnstransfer` account by default.
- Password authentication is the reliable default; SSH public keys remain optional.
- No TCP/agent/X11 forwarding or tunnels.
- Stable SSH host keys are persisted under the app's `/data` directory.
- The account is chrooted to `/config/jns/sftp` and starts in `/incoming`.
- `/incoming` maps directly to the JNS Deployment Platform inbox (`/config/jns/sftp/incoming`).
- The transport account cannot browse JNS trust, backup, transaction or Home Assistant configuration directories.

Keep TCP 2222 LAN/VPN-only. The JNS package signature/hash/path/transaction checks remain the authority for software installation.
