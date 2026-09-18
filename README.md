# JNS Home Assistant Deployment Platform v5.5.0

v5.5 adds **revocable per-management-PC enrollment** while preserving JNS signed-package and transactional deployment protections. It also carries forward the v5.4.2/v5.4.3 Supervisor readiness, provisioning-diagnostic and prebuilt-GHCR SFTP production fixes.

## Replacement-PC workflow

1. Install/update the integration to v5.5.0 through an already authorized administrative path.
2. Open **Settings → Devices & services → JNS Deployment Platform → Configure → Enrol a new management PC**.
3. Home Assistant displays a single-use 20-character code valid for 10 minutes.
4. On JNS Windows Manager v5.5 click **ENROLL THIS PC** and enter the code.
5. The PC submits only its public SFTP/signing keys.
6. Home Assistant creates a dedicated local-only system identity/refresh token, registers the PC's SFTP public key and adds a config-only publisher for that PC.
7. Run **COMMISSION THIS PC** on Windows. It must complete a signed deployment and rollback before legacy credentials can be revoked.

No old private key, SFTP password, HA long-lived token or shared config-signing private key needs to be copied to a new PC.

## Enrollment security

- 100-bit enrollment capability represented as 20 Base32-style characters.
- 10-minute expiry.
- Single use.
- Only SHA-256 of the code is persisted.
- One dedicated HA system identity per management PC.
- One Ed25519 SFTP key per management PC.
- One Ed25519 config publisher per management PC.
- Private key material never enters Home Assistant.
- Per-PC config publishers cannot authorize platform updates.
- Revoke one PC without rotating another PC's credentials.

## SFTP

Normal v5.5 transport is OpenSSH `internal-sftp`, key-only, user `jnstransfer`, host port 2222. JNS Secure SFTP v0.4.0 persists its host key and exports only the Ed25519 public host key for enrollment fingerprint pinning.

Legacy password mode exists only as a recovery/migration path.

When the final management credential is revoked, v5.5 clears/stops SFTP so a stale authorized key cannot remain usable.

## Existing deployment engine

Signed config/integration packages retain:

- Ed25519 publisher validation;
- declared SHA-256 payload hashes;
- path/traversal/archive controls;
- plan/dry-run/config-check;
- transactional install/update/repair/uninstall;
- rollback and audit-chain protections.

## Migration

Existing pre-v5.5 authorized keys and the `jns-config-production` publisher are preserved as legacy credentials during upgrade. They are not automatically revoked. The options flow enables legacy revocation only after at least one v5.5 management PC has been commissioned.
