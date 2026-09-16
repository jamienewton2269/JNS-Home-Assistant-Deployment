# JNS Home Assistant Deployment Platform v5.4.2

## SFTP provisioning repair

This maintenance release improves first-run and repair provisioning of the JNS Secure SFTP companion app.

- Waits for Supervisor repository indexing after registering the JNS App repository instead of assuming immediate availability.
- Waits for the JNS Secure SFTP app to become queryable before attempting installation.
- Separates failures into repository-list, repository-add, repository-discovery, app-discovery, app-install, app-configure and app-start stages.
- Shows the exact failed stage and a sanitized Supervisor error in the Home Assistant config/options flow.
- Keeps the existing HACS-first bootstrap, signed package verification, SFTP-only transport, update/repair/uninstall and rollback model unchanged.

This release is specifically intended to improve live commissioning diagnostics after the first v5.4.1 HACS bootstrap test.
