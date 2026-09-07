from __future__ import annotations

from pathlib import Path
import hashlib
import importlib.util
import json
import sys
import tempfile
import types
import zipfile

ROOT = Path(__file__).resolve().parent.parent
CC = ROOT / "custom_components" / "jns_deployment"


def load_engine():
    package_name = "_jns_beta_test"
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

    return (
        sys.modules[f"{package_name}.const"],
        sys.modules[f"{package_name}.deployment"],
    )


const, engine = load_engine()
DeploymentManager = engine.DeploymentManager


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def make_config_package(path: Path, version="1.0.0"):
    payload = (
        "input_boolean:\n"
        "  beta_flag:\n"
        "    name: Beta Flag\n"
    ).encode()
    manifest = {
        "format": 1,
        "package_id": "beta_test",
        "name": "Beta Test",
        "version": version,
        "files": [{
            "source": "payload/test.yaml",
            "target": "packages/beta_test.yaml",
            "sha256": sha(payload),
        }],
    }
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "jns_package.json",
            json.dumps(manifest, indent=2) + "\n",
        )
        archive.writestr("payload/test.yaml", payload)
    return payload


def make_platform_update(path: Path, from_version: str, to_version: str):
    files = {
        "__init__.py": b"# updated init\n",
        "const.py": f'VERSION = "{to_version}"\n'.encode(),
        "config_flow.py": b"# config flow\n",
        "deployment.py": b"# deployment\n",
        "services.yaml": b"status:\n  name: Status\n",
        "strings.json": b'{"title":"JNS"}\n',
        "translations/en.json": b'{"title":"JNS"}\n',
        "manifest.json": (
            json.dumps(
                {
                    "domain": "jns_deployment",
                    "name": "JNS Home Assistant Deployment Platform",
                    "version": to_version,
                },
                separators=(",", ":"),
            )
            + "\n"
        ).encode(),
    }

    entries = []
    for relative, data in files.items():
        entries.append(
            {
                "source": f"payload/{relative}",
                "target": (
                    "custom_components/jns_deployment/"
                    + relative
                ),
                "sha256": sha(data),
            }
        )

    manifest = {
        "format": 2,
        "type": "platform_update",
        "domain": "jns_deployment",
        "name": f"JNS platform {to_version}",
        "version": to_version,
        "from_version": [from_version],
        "to_version": to_version,
        "files": entries,
    }

    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "jns_package.json",
            json.dumps(manifest, indent=2) + "\n",
        )
        for relative, data in files.items():
            archive.writestr(f"payload/{relative}", data)

    return sha(path.read_bytes())


with tempfile.TemporaryDirectory() as tempdir:
    config = Path(tempdir)

    # Seed a fake existing JNS integration for platform-update tests.
    live_integration = (
        config / "custom_components" / "jns_deployment"
    )
    live_integration.mkdir(parents=True)
    (live_integration / "__init__.py").write_text(
        "# original init\n",
        encoding="utf-8",
    )
    (live_integration / "manifest.json").write_text(
        json.dumps(
            {
                "domain": "jns_deployment",
                "name": "JNS",
                "version": "4.3.0-beta.1",
            }
        ),
        encoding="utf-8",
    )

    manager = DeploymentManager(
        config,
        "jns/inbox",
        "jns/staging",
        "jns/backups",
        "jns/state",
        "jns/platform_updates",
    )

    package_path = config / "jns" / "inbox" / "beta.zip"
    payload = make_config_package(package_path)

    inbox = manager.list_inbox_packages()
    assert inbox["count"] == 1
    assert inbox["packages"][0]["valid"] is True

    plan = manager.plan_package("beta.zip")
    assert plan["change_count"] == 1
    assert plan["changes"][0]["action"] == "create"

    install = manager.install_package("beta.zip", False)
    assert install["installed"] is True
    assert (
        config / "packages" / "beta_test.yaml"
    ).read_bytes() == payload

    installed = manager.list_installed_packages()
    assert installed["count"] == 1
    assert installed["packages"][0]["package_id"] == "beta_test"

    status = manager.get_status("4.3.0-beta.1")
    assert status["version"] == "4.3.0-beta.1"
    assert status["transaction_count"] >= 1

    manager.rollback_transaction(install["transaction_id"])
    assert not (config / "packages" / "beta_test.yaml").exists()

    # Simulate an interrupted create operation and recover it.
    interrupted_id = "20990101T000000Z-interrupted"
    tx_root = config / "jns" / "backups" / interrupted_id
    tx_root.mkdir(parents=True)
    interrupted_target = config / "packages" / "interrupted.yaml"
    interrupted_target.parent.mkdir(parents=True, exist_ok=True)
    interrupted_target.write_text("bad: state\n", encoding="utf-8")
    record = {
        "transaction_id": interrupted_id,
        "kind": "package_install",
        "status": "committing",
        "files": [{
            "target": "packages/interrupted.yaml",
            "action": "create",
            "previously_existed": False,
            "backup_sha256": None,
            "installed_sha256": None,
        }],
    }
    (tx_root / "transaction.json").write_text(
        json.dumps(record),
        encoding="utf-8",
    )

    # New manager load marks it interrupted.
    manager = DeploymentManager(
        config,
        "jns/inbox",
        "jns/staging",
        "jns/backups",
        "jns/state",
        "jns/platform_updates",
    )
    assert manager.get_transaction(interrupted_id)["status"] == "interrupted"
    manager.recover_interrupted_transaction(interrupted_id)
    assert not interrupted_target.exists()

    # Platform update validate/install/confirm/rollback.
    platform_zip = (
        config
        / "jns"
        / "platform_updates"
        / "next_beta.zip"
    )
    archive_hash = make_platform_update(
        platform_zip,
        "4.3.0-beta.1",
        "4.3.0-beta.2",
    )
    validation = manager.validate_platform_update(
        "next_beta.zip",
        archive_hash,
        "4.3.0-beta.1",
    )
    assert validation["to_version"] == "4.3.0-beta.2"

    update = manager.install_platform_update(
        "next_beta.zip",
        archive_hash,
        "4.3.0-beta.1",
        False,
    )
    assert update["requires_restart"] is True
    embedded = json.loads(
        (
            config
            / "custom_components"
            / "jns_deployment"
            / "manifest.json"
        ).read_text(encoding="utf-8")
    )
    assert embedded["version"] == "4.3.0-beta.2"

    confirmed = manager.confirm_pending_platform_update(
        "4.3.0-beta.2"
    )
    assert confirmed and confirmed["status"] == "confirmed"

    manager.rollback_platform_update(update["transaction_id"])
    original = (
        config
        / "custom_components"
        / "jns_deployment"
        / "__init__.py"
    ).read_text(encoding="utf-8")
    assert original == "# original init\n"

print("JNS v4.3.0-beta.1 beta engine self-test: PASS")
print("Inbox discovery: PASS")
print("Deployment planning: PASS")
print("Install/inventory/rollback: PASS")
print("Interrupted transaction recovery: PASS")
print("Platform update validation: PASS")
print("Platform tree replacement/confirmation: PASS")
print("Platform rollback: PASS")
