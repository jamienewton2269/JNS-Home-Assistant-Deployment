# JNS v4.3.0-beta.1 Test Plan

Run tests in this order.

## 1. GitHub/HACS gates

All must be green:
- Hassfest
- HACS validation
- Local static and security checks
- Beta engine self-test

## 2. Install beta through HACS

Restart Home Assistant and confirm:
- Settings > Devices & services shows JNS.
- `jns_deployment.status` returns `4.3.0-beta.1`.
- `/config/jns/state` and `/config/jns/platform_updates` exist.

## 3. Package discovery and planning

Copy `example_packages/jns_v4_3_0_beta_1_test_package.zip` to `/config/jns/inbox`.

Call:
- `jns_deployment.list_inbox_packages`
- `jns_deployment.plan_package`
- `jns_deployment.validate_package`

Expected: valid package, one create/replace target, correct hashes.

## 4. Dry run

Run `install_package` with `dry_run: true`.
Expected: no live file changes and no committed transaction.

## 5. Live install + HA config validation

Run `install_package` with:
- `dry_run: false`
- `check_config: true`

Expected:
- target file installed;
- Home Assistant config check reports passed;
- committed transaction recorded.

## 6. Transaction inspection

Call:
- `list_transactions`
- `get_transaction`
- `list_installed_packages`

Expected: new package appears as active.

## 7. Rollback

Run `rollback_transaction`.
Expected:
- previous state restored;
- post-rollback config check runs.

## 8. Negative package tests

Use ZIPs in `security_test_packages/`.
Every one must fail without changing live files.

## 9. Error message test

Tampered hash must show the real SHA-256 error in the Actions UI rather than
`Unknown error`.

## 10. Drift protection

Install test package, manually edit its target, then request rollback without force.
Expected: rollback refused. Review file, then test `force: true`.

## 11. Interrupted recovery

Use the included engine self-test for automatic coverage. A live power-loss test is
optional during beta and should be performed only on a disposable Home Assistant VM.

## 12. Platform updater

Do not test until a later beta platform-update package is generated. Future test:
- place format-2 package in `/config/jns/platform_updates`;
- enter its published archive SHA-256;
- validate/dry-run/install;
- restart;
- confirm status reports platform update confirmed.
