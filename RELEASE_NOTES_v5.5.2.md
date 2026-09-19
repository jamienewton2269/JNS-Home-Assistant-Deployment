# JNS Deployment Platform v5.5.2

## Enrollment UI, event-loop and Supervisor compatibility hotfix

- Fixes blank labels in the Home Assistant **JNS management-PC security** menu.
- Moves management-PC registry, enrollment-session, trust-store and SFTP host-key
  file I/O off Home Assistant's event loop by using executor jobs.
- Removes the remaining dependency on Supervisor's strict full installed-add-on
  model during JNS Secure SFTP lifecycle operations. This avoids failures when
  Supervisor omits legacy fields such as `hostname`.
- Uses lightweight store/installed add-on list state for install/start/restart/
  stop/status decisions while preserving the v5.4.3 readiness and diagnostics
  behaviour.
- Keeps legacy SFTP keys and the legacy config publisher intact until a newly
  enrolled PC has completed commissioning.

A Windows Manager hotfix accompanies this release and extends the enrollment
HTTP timeout so a legitimate Supervisor SFTP restart cannot cause the desktop
console to abandon enrollment prematurely.
