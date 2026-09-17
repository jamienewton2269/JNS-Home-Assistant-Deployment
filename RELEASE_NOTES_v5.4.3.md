# JNS Home Assistant Deployment Platform v5.4.3

- Publish JNS Secure SFTP as a prebuilt multi-architecture GHCR image and have Supervisor pull it instead of building it on the Home Assistant host.
- Keep the local Dockerfile as the reproducible image source.
- Move DeploymentManager construction and startup filesystem scanning off the Home Assistant event loop.
- Keep signed package validation, transaction, update, repair, uninstall and rollback behavior unchanged.

Live commissioning reason: Supervisor successfully discovered the JNS app repository but failed at `app_install` while attempting to build the SFTP image locally. Using a prebuilt image removes that host-specific build step from production deployments.
