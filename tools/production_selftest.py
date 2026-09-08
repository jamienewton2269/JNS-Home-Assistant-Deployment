from __future__ import annotations

from pathlib import Path
import base64
import hashlib
import importlib.util
import json
import sys
import tempfile
import types
import zipfile

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

ROOT = Path(__file__).resolve().parent.parent
CC = ROOT / "custom_components" / "jns_deployment"
SIGNATURE_DOMAIN = b"JNS-PACKAGE-V3\x00"


def load_modules():
    package_name = "_jns_prod_test"
    package = types.ModuleType(package_name)
    package.__path__ = [str(CC)]
    sys.modules[package_name] = package
    loaded = {}
    for name in ("const", "audit", "security", "deployment"):
        spec = importlib.util.spec_from_file_location(
            f"{package_name}.{name}", CC / f"{name}.py"
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[f"{package_name}.{name}"] = module
        assert spec.loader is not None
        spec.loader.exec_module(module)
        loaded[name] = module
    return loaded


modules = load_modules()
DeploymentManager = modules["deployment"].DeploymentManager
DeploymentError = modules["deployment"].DeploymentError


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def make_trust(config: Path, private_key, publisher_id: str, scopes: list[str]) -> None:
    public_raw = private_key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    trust = config / "jns" / "trust"
    trust.mkdir(parents=True, exist_ok=True)
    (trust / "publishers.json").write_text(
        json.dumps(
            {
                "schema": 1,
                "publishers": [
                    {
                        "id": publisher_id,
                        "name": "Test Publisher",
                        "public_key": base64.b64encode(public_raw).decode("ascii"),
                        "fingerprint_sha256": sha(public_raw),
                        "scopes": scopes,
                        "enabled": True,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def signed_zip(
    path: Path,
    private_key,
    publisher_id: str,
    package_type: str,
    files: list[tuple[str, str, bytes]],
    **extra,
) -> None:
    entries = [
        {"source": source, "target": target, "sha256": sha(data)}
        for source, target, data in files
    ]
    manifest = {
        "format": 3,
        "type": package_type,
        "publisher_id": publisher_id,
        "package_id": extra.pop("package_id", "test_package"),
        "name": extra.pop("name", "Test Package"),
        "version": extra.pop("version", "1.0.0"),
        **extra,
        "files": entries,
    }
    raw_manifest = (json.dumps(manifest, indent=2) + "\n").encode("utf-8")
    signature_bytes = private_key.sign(SIGNATURE_DOMAIN + raw_manifest)
    signature = {
        "algorithm": "ed25519",
        "publisher_id": publisher_id,
        "manifest_sha256": sha(raw_manifest),
        "signature": base64.b64encode(signature_bytes).decode("ascii"),
    }
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("jns_package.json", raw_manifest)
        archive.writestr("jns_signature.json", json.dumps(signature, indent=2) + "\n")
        for source, _target, data in files:
            archive.writestr(source, data)


with tempfile.TemporaryDirectory() as tempdir:
    config = Path(tempdir)
    private_key = Ed25519PrivateKey.generate()
    publisher_id = "test-publisher"
    make_trust(config, private_key, publisher_id, ["config", "platform"])

    live_integration = config / "custom_components" / "jns_deployment"
    live_integration.mkdir(parents=True)
    (live_integration / "__init__.py").write_text("# original\n", encoding="utf-8")
    (live_integration / "manifest.json").write_text(
        json.dumps({"domain": "jns_deployment", "name": "JNS", "version": "5.0.0"}),
        encoding="utf-8",
    )

    manager = DeploymentManager(
        config,
        "jns/inbox",
        "jns/staging",
        "jns/backups",
        "jns/state",
        "jns/platform_updates",
        "jns/trust",
        "jns/audit",
        "jns/quarantine",
        "jns/recovery",
    )

    payload = b"input_boolean:\n  production_test:\n    name: Production Test\n"
    config_zip = config / "jns" / "inbox" / "signed.zip"
    signed_zip(
        config_zip,
        private_key,
        publisher_id,
        "config_package",
        [("payload/test.yaml", "packages/production_test.yaml", payload)],
        package_id="production_test",
    )
    validation = manager.validate_package("signed.zip")
    assert validation["signed"] is True
    assert validation["publisher_id"] == publisher_id
    plan = manager.plan_package("signed.zip")
    assert plan["changes"][0]["action"] == "create"
    install = manager.install_package("signed.zip", False)
    target = config / "packages" / "production_test.yaml"
    assert target.read_bytes() == payload
    assert manager.verify_audit_log()["entries"] >= 2
    manager.rollback_transaction(install["transaction_id"])
    assert not target.exists()

    # Untrusted publisher.
    attacker_key = Ed25519PrivateKey.generate()
    bad_zip = config / "jns" / "inbox" / "unknown.zip"
    signed_zip(
        bad_zip,
        attacker_key,
        "attacker",
        "config_package",
        [("payload/test.yaml", "packages/unknown.yaml", payload)],
    )
    try:
        manager.validate_package("unknown.zip")
    except DeploymentError as exc:
        assert "not trusted" in str(exc)
    else:
        raise AssertionError("Untrusted publisher was accepted")

    # Tampered payload after a valid signature.
    tamper_zip = config / "jns" / "inbox" / "tampered.zip"
    signed_zip(
        tamper_zip,
        private_key,
        publisher_id,
        "config_package",
        [("payload/test.yaml", "packages/tampered.yaml", payload)],
    )
    with zipfile.ZipFile(tamper_zip, "r") as source:
        manifest_raw = source.read("jns_package.json")
        signature_raw = source.read("jns_signature.json")
    with zipfile.ZipFile(tamper_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("jns_package.json", manifest_raw)
        archive.writestr("jns_signature.json", signature_raw)
        archive.writestr("payload/test.yaml", payload + b"# modified\n")
    try:
        manager.validate_package("tampered.zip")
    except DeploymentError as exc:
        assert "SHA-256 mismatch" in str(exc)
    else:
        raise AssertionError("Tampered payload was accepted")

    # Unsigned package.
    unsigned = config / "jns" / "inbox" / "unsigned.zip"
    with zipfile.ZipFile(unsigned, "w") as archive:
        archive.writestr(
            "jns_package.json",
            json.dumps(
                {
                    "format": 1,
                    "name": "unsigned",
                    "version": "1.0.0",
                    "files": [{"source": "x", "target": "packages/x.yaml", "sha256": "0" * 64}],
                }
            ),
        )
        archive.writestr("x", b"x")
    try:
        manager.validate_package("unsigned.zip")
    except DeploymentError as exc:
        assert "jns_signature.json" in str(exc)
    else:
        raise AssertionError("Unsigned package was accepted")

    # Platform update.
    platform_files = {
        "__init__.py": b"# new init\n",
        "const.py": b'VERSION = "5.0.1"\n',
        "config_flow.py": b"# flow\n",
        "deployment.py": b"# deployment\n",
        "security.py": b"# security\n",
        "audit.py": b"# audit\n",
        "services.yaml": b"status:\n  name: Status\n",
        "recovery_tool.py": b"# recovery\n",
        "diagnostics.py": b"# diagnostics\n",
        "manifest.json": (
            json.dumps({"domain": "jns_deployment", "name": "JNS", "version": "5.0.1"})
            + "\n"
        ).encode(),
    }
    platform_zip = config / "jns" / "platform_updates" / "platform.zip"
    signed_zip(
        platform_zip,
        private_key,
        publisher_id,
        "platform_update",
        [
            (f"payload/{name}", f"custom_components/jns_deployment/{name}", data)
            for name, data in platform_files.items()
        ],
        package_id="jns_platform",
        domain="jns_deployment",
        from_version=["5.0.0"],
        to_version="5.0.1",
        version="5.0.1",
    )
    platform_validation = manager.validate_platform_update("platform.zip", "5.0.0")
    assert platform_validation["to_version"] == "5.0.1"
    update = manager.install_platform_update("platform.zip", "5.0.0", False)
    assert update["requires_restart"] is True
    confirmed = manager.confirm_pending_platform_update("5.0.1")
    assert confirmed and confirmed["status"] == "confirmed"
    manager.rollback_platform_update(update["transaction_id"])
    assert (config / "custom_components" / "jns_deployment" / "__init__.py").read_text(
        encoding="utf-8"
    ) == "# original\n"

    # Audit tamper detection.
    audit_path = config / "jns" / "audit" / "audit.jsonl"
    lines = audit_path.read_text(encoding="utf-8").splitlines()
    record = json.loads(lines[0])
    record["event"] = "tampered_event"
    lines[0] = json.dumps(record, separators=(",", ":"), sort_keys=True)
    audit_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        manager.verify_audit_log()
    except DeploymentError as exc:
        assert "hash mismatch" in str(exc).lower()
    else:
        raise AssertionError("Tampered audit log was accepted")

print("JNS v5.0.0 production self-test: PASS")
print("Trusted Ed25519 signed config package: PASS")
print("Untrusted publisher rejection: PASS")
print("Tampered payload rejection: PASS")
print("Unsigned legacy package rejection: PASS")
print("Signed platform update/confirm/rollback: PASS")
print("Audit-chain tamper detection: PASS")
