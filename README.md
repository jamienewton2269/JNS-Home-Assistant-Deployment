# JNS Home Assistant Deployment Platform v5.0.0

JNS v5 is the production security baseline for signed, transactional Home Assistant configuration deployment and JNS platform self-updates.

## Production trust model

All deployable packages must be **Ed25519 signed by a trusted publisher**. JNS verifies the exact manifest signature, trusted publisher scope, every payload SHA-256, archive policy and target policy before any live file is changed.

Private publisher keys stay off Home Assistant. Home Assistant stores only trusted public keys in:

`/config/jns/trust/publishers.json`

## Trust bootstrap

On a trusted workstation:

```bash
python tools/jns_keygen.py --publisher-id jns-production --name "JNS Production Publisher"
python tools/jns_make_trust_store.py \
  --public-key jns_keys/jns-production.public.json \
  --scope config --scope platform \
  --output publishers.json
```

Copy only `publishers.json` to `/config/jns/trust/publishers.json` using SSH/SFTP. Never copy the `.private.pem` key to Home Assistant.

## Signing a configuration package

```bash
python tools/jns_sign_package.py \
  --input unsigned_package.zip \
  --output signed_package.zip \
  --private-key jns_keys/jns-production.private.pem \
  --publisher-id jns-production \
  --type config_package \
  --package-id my_package
```

Transfer the signed ZIP to `/config/jns/inbox`.

## Production workflow

`SFTP -> inbox -> publisher signature -> SHA-256 -> plan -> dry run -> install -> HA config check -> transaction/audit`

Actions include status, trusted publisher listing, audit verification, inbox discovery, planning, validation, install, quarantine, rollback, interrupted recovery, transaction history, installed package inventory and signed platform updates.

## Security controls

v5 includes mandatory signatures, publisher scopes, package path/extension allow-lists, symlink/special-file rejection, undeclared file rejection, ZIP size/compression-ratio protection, disk-space reserve checks, durable atomic writes, transaction backups, post-commit hash checks, file/process locking, drift-protected rollback, interrupted transaction recovery, signed platform updates, stable emergency recovery and a tamper-evident hash-chained audit log.

Unsigned v4 packages are intentionally rejected.

## Platform updates

Platform publishers require the `platform` scope. Build a future update with:

```bash
python tools/jns_build_platform_update.py \
  --repo . \
  --private-key jns_keys/jns-production.private.pem \
  --publisher-id jns-production \
  --from-version 5.0.0 \
  --to-version 5.0.1 \
  --output JNS_Platform_5.0.1.zip
```

Transfer it to `/config/jns/platform_updates`, validate/dry-run/install, then restart Home Assistant.

## Emergency recovery

A stable standalone recovery utility is copied to:

`/config/jns/recovery/jns_emergency_recover.py`

Example:

```bash
python3 /config/jns/recovery/jns_emergency_recover.py \
  --config /config \
  --transaction TRANSACTION_ID
```

Then restart Home Assistant.

## Upgrade from v4.x

Use HACS for the v4.x -> v5.0.0 transition. Once v5 is installed and publisher trust is bootstrapped, future JNS platform updates can use signed platform packages.

See `PRODUCTION_ACCEPTANCE.md` before enabling unattended deployment.
