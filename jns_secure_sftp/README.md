# JNS Secure SFTP 0.4.0

A deliberately small Home Assistant App used only to transport JNS deployment packages.

## v5.5 management-PC enrollment

Normal v5.5 operation is public-key only. Each enrolled JNS Windows management PC generates its own Ed25519 SSH key locally. Home Assistant stores only that PC's public key. The private key never leaves the PC and is protected there by Windows DPAPI.

The App persists its server host keys under `/data` and exports only the Ed25519 **public** host key to `/homeassistant/jns/sftp/server_host_ed25519.pub`. The Home Assistant enrollment response returns that trusted fingerprint so the Windows console can pin the SFTP server without blind trust-on-first-use.

Legacy password authentication remains supported for migration/recovery but is disabled automatically once enrolled management-PC public keys are applied.

## Security boundary

- OpenSSH `internal-sftp` only; no interactive shell.
- Dedicated non-root `jnstransfer` account.
- Public-key-only authentication in normal v5.5 operation.
- No TCP/agent/X11 forwarding or tunnels.
- Stable SSH host keys persisted under the App's `/data` directory.
- Account chrooted to `/config/jns/sftp` and starts in `/incoming`.
- `/incoming` maps directly to the JNS Deployment Platform inbox.
- Transfer account cannot browse trust, backup, transaction or general Home Assistant configuration directories.

Keep TCP 2222 LAN/VPN-only. JNS signature/hash/path/transaction checks remain the authority for installation.
