from __future__ import annotations

from pathlib import Path
import hashlib
import importlib.util
import json
import stat
import sys
import tempfile
import types
import zipfile

ROOT = Path(__file__).resolve().parent.parent
CC = ROOT / "custom_components" / "jns_deployment"


def load_engine():
    package_name = "_jns_security_test"
    package = types.ModuleType(package_name)
    package.__path__ = [str(CC)]
    sys.modules[package_name] = package

    for module_name in ("const", "deployment"):
        spec = importlib.util.spec_from_file_location(
            f"{package_name}.{module_name}",
            CC / f"{module_name}.py",
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[f"{package_name}.{module_name}"] = module
        assert spec.loader is not None
        spec.loader.exec_module(module)

    return sys.modules[f"{package_name}.deployment"]


engine = load_engine()
DeploymentManager = engine.DeploymentManager
DeploymentError = engine.DeploymentError


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def make_zip(path: Path, manifest: dict, members):
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "jns_package.json",
            json.dumps(manifest, indent=2) + "\n",
        )
        for member in members:
            if isinstance(member, zipfile.ZipInfo):
                archive.writestr(member, b"symlink-target")
            else:
                name, data = member
                archive.writestr(name, data)


def expect_rejected(manager, package_name, expected_text):
    try:
        manager.validate_package(package_name)
    except DeploymentError as exc:
        if expected_text.lower() not in str(exc).lower():
            raise AssertionError(
                f"{package_name}: expected {expected_text!r}; got {str(exc)!r}"
            )
    else:
        raise AssertionError(f"{package_name}: package was unexpectedly accepted")


with tempfile.TemporaryDirectory() as tempdir:
    config = Path(tempdir)
    manager = DeploymentManager(
        config,
        "jns/inbox",
        "jns/staging",
        "jns/backups",
        "jns/state",
        "jns/platform_updates",
    )
    inbox = config / "jns" / "inbox"

    valid = (
        "input_boolean:\n"
        "  jns_test_flag:\n"
        "    name: JNS Test\n"
    ).encode()

    def manifest_for(source, target, digest_value, name="test"):
        return {
            "format": 1,
            "package_id": name,
            "name": name,
            "version": "1.0.0",
            "files": [{
                "source": source,
                "target": target,
                "sha256": digest_value,
            }],
        }

    make_zip(
        inbox / "valid.zip",
        manifest_for(
            "payload/test.yaml",
            "packages/test.yaml",
            sha(valid),
            "valid",
        ),
        [("payload/test.yaml", valid)],
    )
    result = manager.install_package("valid.zip", False)
    target = config / "packages" / "test.yaml"
    assert target.is_file()
    manager.rollback_transaction(result["transaction_id"])
    assert not target.exists()

    make_zip(
        inbox / "tampered.zip",
        manifest_for(
            "payload/test.yaml",
            "packages/test.yaml",
            sha(valid),
            "tampered",
        ),
        [("payload/test.yaml", valid + b"# changed\n")],
    )
    expect_rejected(manager, "tampered.zip", "sha-256 mismatch")

    make_zip(
        inbox / "traversal.zip",
        manifest_for(
            "../escape.yaml",
            "packages/test.yaml",
            sha(valid),
            "traversal",
        ),
        [("../escape.yaml", valid)],
    )
    expect_rejected(manager, "traversal.zip", "unsafe package path")

    make_zip(
        inbox / "undeclared.zip",
        manifest_for(
            "payload/test.yaml",
            "packages/test.yaml",
            sha(valid),
            "undeclared",
        ),
        [
            ("payload/test.yaml", valid),
            ("payload/extra.txt", b"extra"),
        ],
    )
    expect_rejected(manager, "undeclared.zip", "undeclared files")

    pydata = b"print('never executed')\n"
    make_zip(
        inbox / "code.zip",
        manifest_for(
            "payload/evil.py",
            "custom_components/evil/__init__.py",
            sha(pydata),
            "code",
        ),
        [("payload/evil.py", pydata)],
    )
    expect_rejected(manager, "code.zip", "outside jns allowed roots")

    link = zipfile.ZipInfo("payload/link.yaml")
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    make_zip(
        inbox / "symlink.zip",
        manifest_for(
            "payload/link.yaml",
            "packages/test.yaml",
            sha(b"symlink-target"),
            "symlink",
        ),
        [link],
    )
    expect_rejected(manager, "symlink.zip", "special files")

    second = b"input_boolean:\n  second:\n    name: second\n"
    duplicate_manifest = {
        "format": 1,
        "package_id": "duplicate",
        "name": "duplicate",
        "version": "1.0.0",
        "files": [
            {
                "source": "payload/one.yaml",
                "target": "packages/test.yaml",
                "sha256": sha(valid),
            },
            {
                "source": "payload/two.yaml",
                "target": "packages/test.yaml",
                "sha256": sha(second),
            },
        ],
    }
    make_zip(
        inbox / "duplicate.zip",
        duplicate_manifest,
        [
            ("payload/one.yaml", valid),
            ("payload/two.yaml", second),
        ],
    )
    expect_rejected(manager, "duplicate.zip", "target more than once")

    bomb = b"A" * (1024 * 1024)
    make_zip(
        inbox / "ratio.zip",
        manifest_for(
            "payload/test.yaml",
            "packages/test.yaml",
            sha(bomb),
            "ratio",
        ),
        [("payload/test.yaml", bomb)],
    )
    expect_rejected(manager, "ratio.zip", "compression ratio")

    # Drift protection.
    make_zip(
        inbox / "drift.zip",
        manifest_for(
            "payload/test.yaml",
            "packages/drift.yaml",
            sha(valid),
            "drift",
        ),
        [("payload/test.yaml", valid)],
    )
    result = manager.install_package("drift.zip", False)
    drift_target = config / "packages" / "drift.yaml"
    drift_target.write_bytes(valid + b"# user changed\n")
    try:
        manager.rollback_transaction(result["transaction_id"])
    except DeploymentError as exc:
        assert "changed after deployment" in str(exc)
    else:
        raise AssertionError("Rollback drift protection did not trigger")

    manager.rollback_transaction(result["transaction_id"], force=True)
    assert not drift_target.exists()

print("JNS v4.3.0-beta.1 security self-test: PASS")
print("Valid install/rollback: PASS")
print("Tampered SHA-256 rejection: PASS")
print("Path traversal rejection: PASS")
print("Undeclared file rejection: PASS")
print("Forbidden code-target rejection: PASS")
print("Symlink/special-file rejection: PASS")
print("Duplicate-target rejection: PASS")
print("Compression-ratio rejection: PASS")
print("Rollback drift protection: PASS")
