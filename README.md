# JNS Home Assistant Deployment Platform v4.2.3

JNS is a Home Assistant deployment, configuration and rollback layer designed to sit above normal Home Assistant/HACS installation mechanisms.

This is a controlled test baseline.

## Security model

JNS treats deployment packages as untrusted. It validates archive paths, rejects symbolic links and undeclared files, verifies per-file SHA-256 values, restricts deployment targets, stages files before commit, keeps rollback copies, and never executes package-provided commands. SSH/SFTP remains the standard remote transport mechanism.

## HACS installation

Repository: `https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment`

Add it to HACS as a custom repository with category **Integration**, install it, restart Home Assistant, then add **JNS Home Assistant Deployment Platform** from Settings > Devices & services.

## Package inbox

Deployment packages are placed in `/config/jns/inbox`. Use SFTP/SSH for remote transfer.

## Services

- `jns_deployment.validate_package`
- `jns_deployment.install_package`
- `jns_deployment.rollback_transaction`

## GitHub repository metadata required by HACS

Description: `Transactional deployment, validation and rollback platform for Home Assistant, installable via HACS.`

Topics: `home-assistant`, `hacs`, `custom-component`, `deployment`, `rollback`

GitHub Issues must remain enabled.

## Test warning

This is a development/testing build. Do not use it for unattended production deployment until power-loss handling, concurrent deployment locking, trusted package signing, and additional integration testing are complete.
