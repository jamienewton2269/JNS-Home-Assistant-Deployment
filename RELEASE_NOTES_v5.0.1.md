# JNS Home Assistant Deployment Platform v5.0.1

Production hotfix for Home Assistant configuration-check result handling.

v5.0.0 incorrectly treated the truthiness of the returned `HomeAssistantConfig`
object as failure. A valid result is normally populated and therefore truthy.
v5.0.1 checks `result.errors` and reports `result.warnings` as non-fatal warnings.
Automatic rollback remains enabled for genuine configuration errors.
