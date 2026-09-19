# JNS Deployment Platform v5.5.3

## Supervisor options-read enrollment hotfix

This release fixes management-PC enrollment on Home Assistant/Supervisor builds
where the dedicated `/addons/<slug>/options/config` endpoint rejects requests
from Home Assistant Core with HTTP 403 and the message
"This can be only read by the app itself!".

### Changes

- Reads JNS Secure SFTP options from Supervisor's normal app-info endpoint,
  which is permitted to Home Assistant Core.
- Uses the raw app-info response so enrollment does not depend on the strict
  installed-add-on model fields that caused the earlier missing-`hostname`
  failure.
- Preserves legacy authorized SSH keys while adding the new management-PC key.
- Stops using the app-self-only `options/config` endpoint anywhere in the JNS
  integration.
- Returns a sanitized stage-specific enrollment error to the Windows Manager
  instead of the generic `enrollment_failed` response for SFTP provisioning
  failures.
- Keeps the v5.5.2 event-loop-safe management registry/session/trust I/O fixes.

No Windows-side protocol change is required. JNS Windows Management Console
v5.5.2 remains compatible with this server-side hotfix.
