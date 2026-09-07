# JNS Home Assistant Deployment Platform v4.3.0-beta.1

JNS is a transactional deployment, validation, recovery and rollback layer for
Home Assistant. The beta is intended for controlled live testing.

## Beta capabilities

### Package workflow

1. Transfer a package by standard SSH/SFTP to `/config/jns/inbox`.
2. `list_inbox_packages` discovers and validates available packages.
3. `plan_package` reports create/replace/unchanged targets.
4. `validate_package` verifies package structure, policy and SHA-256 values.
5. `install_package` stages, verifies, backs up and commits the transaction.
6. Home Assistant's own configuration validation runs by default after commit.
7. If Home Assistant configuration validation fails, JNS automatically rolls the
   transaction back.
8. Transactions can be inspected and rolled back later.

### Security policy

Unsigned format-1 packages may write only:

- `packages/` — YAML
- `themes/` — YAML
- `www/jns/` — static web content

They cannot deploy executable Python or write to `custom_components/`.

JNS rejects traversal paths, duplicate members/targets, undeclared files, special
files/symlinks, encrypted ZIP members, disallowed extensions, oversized archives,
excessive compression ratios and SHA-256 mismatches.

### Recovery

Transaction intent is persisted before each live file replacement. Transactions left
in `staging` or `committing` state are marked `interrupted` when JNS next loads.
`recover_interrupted_transaction` explicitly restores the recorded pre-transaction
state.

### Rollback drift protection

Normal rollback refuses to overwrite a target changed after JNS installed it. A
`force: true` rollback is available only as an explicit operator decision.

### Platform self-update

Beta adds format-2 platform updates under:

`/config/jns/platform_updates`

A platform update can replace only the complete
`custom_components/jns_deployment/` tree and requires the operator to supply an
explicit expected SHA-256 for the entire archive. The internal files are also
individually hash checked and all Python is compiled before commit.

This is a controlled beta trust model, not a substitute for publisher signatures.
A signed publisher-key format remains planned for production.

After a platform update, restart Home Assistant. The new version confirms the pending
update only after its config entry loads successfully.

## Home Assistant actions

- `jns_deployment.status`
- `jns_deployment.list_inbox_packages`
- `jns_deployment.plan_package`
- `jns_deployment.validate_package`
- `jns_deployment.install_package`
- `jns_deployment.rollback_transaction`
- `jns_deployment.recover_interrupted_transaction`
- `jns_deployment.list_transactions`
- `jns_deployment.get_transaction`
- `jns_deployment.list_installed_packages`
- `jns_deployment.validate_platform_update`
- `jns_deployment.install_platform_update`
- `jns_deployment.rollback_platform_update`

Expected package/security failures use Home Assistant `ServiceValidationError`, so the
Actions UI reports the actual failure rather than a generic Unknown error.

## Directories

- `/config/jns/inbox`
- `/config/jns/staging`
- `/config/jns/backups`
- `/config/jns/state`
- `/config/jns/platform_updates`

## Installation / beta upgrade

Install through HACS from:

`https://github.com/jamienewton2269/JNS-Home-Assistant-Deployment`

The current v4.2.4 build intentionally cannot deploy executable integration code, so
the **first upgrade from v4.2.4 to this beta must be performed through HACS/GitHub**.
Once beta is installed, later JNS builds can be tested through the trusted-hash
platform-update action.

## Local tests

```bash
python tools/verify_repository.py
python tools/security_selftest.py
python tools/beta_selftest.py
```

All three run in GitHub Actions.

## Beta limitations

- Platform self-update uses operator-supplied archive SHA-256 rather than publisher
  signatures.
- If a platform update is installed and the replacement integration cannot load at
  all after restart, recovery requires HACS or SSH/manual restoration from the
  transaction backup.
- Normal package deployment is file-oriented; dependency-aware ordering and a richer
  native frontend are future work.
