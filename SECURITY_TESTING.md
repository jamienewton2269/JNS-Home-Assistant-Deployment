# JNS v5.0.0 Security Testing

Production CI generates ephemeral Ed25519 keys and verifies trusted signed package acceptance, untrusted publisher rejection, payload tamper rejection, unsigned-package rejection, signed platform update/rollback and audit-chain tamper detection.

`PRODUCTION_ACCEPTANCE.md` defines the additional live Home Assistant tests required before unattended deployment.
