# JNS Deployment Platform v5.5.6

## Current Home Assistant App packaging alignment

This production patch updates the JNS Secure SFTP companion App to the current Home Assistant publishing model without changing the SFTP protocol or management-PC enrollment contract.

### Changes

- JNS Secure SFTP App is updated to v0.4.3.
- The App now references the generic multi-architecture GHCR image:
  `ghcr.io/jamienewton2269/jns-secure-sftp`.
- GitHub Actions now uses Home Assistant builder 2026.09.0 composable actions.
- amd64 and aarch64 images are still built separately, then published as a generic multi-architecture manifest.
- The App remains pre-built; Home Assistant does not build the SFTP container locally.
- The Dockerfile already uses an explicit pinned Home Assistant base image and current `io.hass.type="app"` labels, so it does not rely on the removed Supervisor `BUILD_FROM` fallback.
- Existing SFTP host keys, authorized management-PC keys, chrooting, no-shell policy and deployment signature checks are unchanged.

### Production versions

- JNS Deployment Platform: **5.5.6**
- JNS Secure SFTP App: **0.4.3**
- Supported App architectures: **amd64**, **aarch64**

This change is intended to remove the legacy architecture-placeholder dependency from the runtime App configuration and use the generic manifest image preferred by current Home Assistant.
