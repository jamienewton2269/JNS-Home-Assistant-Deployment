# JNS ScamShield Windows validation

This folder is a **validation scaffold**, not a signed installer or customer release.

- Source: `src/ScamShield.ps1`, read-only audit entry point.
- GitHub workflow: `.github/workflows/scamshield-windows-validation.yml`.
- Windows CI parses script, runs a non-mutating Defender/browser-policy audit, checks report structure, and uploads audit JSON.
- Windows CI **does not** certify policy enforcement, malware resistance, tamper protection, browser behavior, reboot persistence, uninstall correctness, or SmartScreen reputation.
- Signing and publication are deliberately excluded until publisher validation and manual customer-acceptance testing are complete.

## Next quality gates
1. Import reviewed v0.3 policy engine after correcting its backup and policy-ownership behavior.
2. Add isolated tests for install, reboot, tamper detection, supported-browser policies, repairs, uninstall and rollback.
3. Test a clean Windows 11 VM and a physical customer-class Windows 11 device.
4. Choose and verify a UK sole-trader-eligible public code signing provider.
5. Sign and verify each binary/installer in an isolated approved release job.
6. Publish only a tested, correctly signed installer and checksum to the JNS Cloudflare website.

The GitHub Node C runner hosts infrastructure deployments; it must not be used as a substitute for Windows OS validation.
