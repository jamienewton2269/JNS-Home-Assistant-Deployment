# JNS Home Assistant Deployment Platform v5.4.3

- Publish JNS Secure SFTP as a prebuilt multi-architecture GHCR image and have Supervisor pull it instead of building it on the Home Assistant host.
- Keep the local Dockerfile as the reproducible image source.
- Force a Supervisor App Store refresh when the JNS repository is already registered, so repaired app metadata is picked up before install/update.
- Keep signed package validation, transaction, update, repair, uninstall and rollback behavior unchanged.

Live commissioning reason: Supervisor successfully discovered the JNS app repository but failed at `app_install` while attempting to build the SFTP image locally. Using a prebuilt image removes that host-specific build step from production deployments.

The separate Home Assistant event-loop warning caused by DeploymentManager startup filesystem I/O remains tracked as issue #3 and is not treated as the cause of this SFTP installation failure.
