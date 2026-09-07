# JNS v4.2 Test Checklist

## Gate 1 — GitHub
- Push repository to a public GitHub test repository.
- Confirm `Validate` GitHub Action passes:
  - Hassfest
  - HACS validation
  - Local static checks
- Create a GitHub Release tagged `v4.2.0-test.1` if desired.

## Gate 2 — HACS installation
- HACS > three-dot menu > Custom repositories.
- Add the repository URL.
- Category: Integration.
- Install JNS Home Assistant Deployment Platform.
- Restart Home Assistant.
- Settings > Devices & services > Add integration > JNS Home Assistant Deployment Platform.

## Gate 3 — Safe package validation
- Place `example_packages/jns_v4_2_test_package.zip` into `/config/jns/inbox`.
- Call `jns_deployment.validate_package`.
- Confirm a `jns_deployment_validation_result` event reports `ok: true`.
- Confirm no live file was changed.

## Gate 4 — Transactional install
- Call `jns_deployment.install_package` with:
  - package: `jns_v4_2_test_package.zip`
  - dry_run: false
- Confirm `/config/packages/jns_test_package.yaml` appears.
- Record the returned transaction ID.
- Run Home Assistant configuration validation before restart/reload.

## Gate 5 — Rollback
- Call `jns_deployment.rollback_transaction` with the recorded transaction ID.
- Confirm the test package file is removed/restored appropriately.
- Run Home Assistant configuration validation again.

## Do not yet use for production
The test baseline has static validation and transactional rollback logic but has not
been proven against power loss, disk-full conditions, concurrent deployments, package
signing/trust enforcement, or every Home Assistant installation type.
