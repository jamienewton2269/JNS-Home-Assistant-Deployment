# JNS v4.3.0-beta.1 Security Tests

CI runs both `security_selftest.py` and `beta_selftest.py`.

The negative package set verifies rejection of:
- modified payload hashes;
- path traversal;
- undeclared archive members;
- executable-code targets in ordinary packages;
- symlink/special files;
- duplicate targets;
- excessive compression ratios.

The beta self-test additionally verifies:
- package discovery and planning;
- install/active-package inventory/rollback;
- interrupted transaction recovery;
- trusted-hash platform-update validation;
- complete integration-tree replacement;
- post-restart confirmation state;
- platform rollback.

Live beta testing should continue to verify that all expected rejections leave
`/config/packages` and committed transaction state unchanged.
