# JNS Home Assistant Deployment Platform v5.1.1

## Integration-package deployment repair

- Fixes the managed `integration_package` validator using the wrong `ValidatedFile` attribute while mapping target paths back to ZIP members.
- Restores transactional deployment of signed JNS custom integrations under `custom_components/jns_<domain>/`.
- Keeps configuration companion payloads under `packages/`, `themes/`, and `www/jns/`.
- Existing package update, stale-file removal, drift protection, rollback and uninstall logic now applies to managed integrations as intended.
- Integration packages require a Home Assistant restart.

## Regression coverage

Adds an install → drift/repair → update → uninstall integration-package regression test.
