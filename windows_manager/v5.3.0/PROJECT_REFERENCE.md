# JNS Home Assistant Windows Management Console v5.3.0 — Production Reference Point

Status: **LATEST / PRODUCTION REFERENCE**  
Reference date: **2026-09-16**

This version is the new baseline for future JNS Windows Management Console development. It consolidates the working v5.2.x secure-transfer fixes into a single clean reference release. Future work should branch from **v5.3.0** rather than from the intermediate v5.2.5/v5.2.6/v5.2.7 patch packages.

## Reference architecture

- JNS Deployment Platform: **v5.0.1**.
- JNS Secure Transfer Gateway: **v0.2.2**.
- SFTP user: `jnstransfer`.
- SFTP external port: `2222`.
- Gateway drop zone: `/incoming`.
- Gateway handoff target: `/homeassistant/jns/inbox`.
- Windows SSH private-key default: `%USERPROFILE%\.ssh\jns_transfer_2026`.
- Dedicated JNS SSH trust file: `%USERPROFILE%\.ssh\jns_gateway_known_hosts`.
- Current Gateway ED25519 fingerprint: `SHA256:FwI9RHfgiV3sJ0Ow1R6US18DIrS6Haqg7ZD6DZpLVk8`.
- Production JNS config publisher: `jns-config-production`.
- Publisher public-key fingerprint: `d68f9bff1f34aebb6bae4f740bbed48a5fa803a5152a680daf1fd5582fd39431`.

Private SSH keys, publisher private keys, passphrases and Home Assistant access tokens are **not** part of this reference point.

## Security policy fixed at this reference

1. Local/private SSH server with matching trusted key: connect normally.
2. New local/private SSH host key: display the SHA-256 fingerprint and require explicit operator approval before any upload.
3. Changed local/private SSH host key: display previous and current fingerprints and require explicit operator approval before replacing the JNS pin.
4. Non-local/public unknown or changed SSH host key: reject by default.
5. The JNS client uses only its dedicated JNS `known_hosts` file for deployment trust; unrelated Windows/global SSH host keys cannot override it.
6. Paramiko remains `RejectPolicy`; there is no silent `AutoAddPolicy`.
7. Encrypted SSH private-key passphrases are handled through the Windows DPAPI vault.
8. Before signing/uploading an unsigned config package, the Manager synchronizes with Home Assistant's live trusted-publisher list and matches the local signing-key fingerprint to an enabled publisher with `config` scope.
9. If the local signing key is not trusted, deployment stops **before upload**.
10. Gateway signature/trust/hash validation, JNS validation, plan, dry-run/config-check, transactional install, rollback and audit protections remain mandatory.

## Routine deployment path

`select package -> preflight connection -> resolve trusted publisher -> sign -> verify -> SFTP /incoming -> Gateway handoff -> JNS validate -> plan -> dry-run/config check -> transactional install`

## Development rule

Future Windows Manager work should use this branch/reference as the starting baseline and should not reintroduce the superseded v5.2.x SSH trust or publisher-id behaviour.
