# JNS Security Policy

Production JNS v5 accepts only format-3 Ed25519-signed packages. The signing public key must be explicitly trusted in `/config/jns/trust/publishers.json` and have the required scope.

Private signing keys must be generated on a trusted workstation, passphrase protected, kept off Home Assistant, never committed to Git and backed up securely offline.

If a publisher key is suspected compromised: disable/remove its trust entry, verify the audit log, review transactions from that publisher, rotate the key and re-sign future packages.

The trust store is intentionally outside package deployment roots. Modify it only through trusted local administration using SSH/SFTP.
