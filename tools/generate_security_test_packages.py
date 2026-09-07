from pathlib import Path
import hashlib
import json
import stat
import zipfile

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "security_test_packages"
OUT.mkdir(parents=True, exist_ok=True)

VALID_PAYLOAD = (
    "input_boolean:\n"
    "  jns_test_flag:\n"
    "    name: JNS Security Test\n"
    "    icon: mdi:shield-check\n"
)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def manifest(files, name):
    return {
        "format": 1,
        "name": name,
        "version": "1.0.0-negative",
        "files": files,
    }


def write_zip(path, manifest_data, members):
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "jns_package.json",
            json.dumps(manifest_data, indent=2) + "\n",
        )
        for member in members:
            if isinstance(member, zipfile.ZipInfo):
                archive.writestr(member, b"symlink-target")
            else:
                name, data = member
                archive.writestr(name, data)


valid_bytes = VALID_PAYLOAD.encode()

# 1: tampered hash
tampered = VALID_PAYLOAD.replace("Security Test", "TAMPERED").encode()
write_zip(
    OUT / "01_tampered_hash.zip",
    manifest(
        [{
            "source": "payload/test.yaml",
            "target": "packages/security_test.yaml",
            "sha256": digest(valid_bytes),
        }],
        "Tampered hash",
    ),
    [("payload/test.yaml", tampered)],
)

# 2: path traversal
write_zip(
    OUT / "02_path_traversal.zip",
    manifest(
        [{
            "source": "../escape.yaml",
            "target": "packages/security_test.yaml",
            "sha256": digest(valid_bytes),
        }],
        "Path traversal",
    ),
    [("../escape.yaml", valid_bytes)],
)

# 3: undeclared file
write_zip(
    OUT / "03_undeclared_file.zip",
    manifest(
        [{
            "source": "payload/test.yaml",
            "target": "packages/security_test.yaml",
            "sha256": digest(valid_bytes),
        }],
        "Undeclared file",
    ),
    [
        ("payload/test.yaml", valid_bytes),
        ("payload/undeclared.txt", b"must be rejected"),
    ],
)

# 4: forbidden code target
write_zip(
    OUT / "04_forbidden_custom_component.zip",
    manifest(
        [{
            "source": "payload/evil.py",
            "target": "custom_components/evil/__init__.py",
            "sha256": digest(b"print('not executed')\n"),
        }],
        "Forbidden code target",
    ),
    [("payload/evil.py", b"print('not executed')\n")],
)

# 5: symbolic link
link = zipfile.ZipInfo("payload/link.yaml")
link.create_system = 3
link.external_attr = (stat.S_IFLNK | 0o777) << 16
write_zip(
    OUT / "05_symlink.zip",
    manifest(
        [{
            "source": "payload/link.yaml",
            "target": "packages/security_test.yaml",
            "sha256": digest(b"symlink-target"),
        }],
        "Symlink",
    ),
    [link],
)

# 6: duplicate target
second = b"input_boolean:\n  second_flag:\n    name: Second\n"
write_zip(
    OUT / "06_duplicate_target.zip",
    manifest(
        [
            {
                "source": "payload/one.yaml",
                "target": "packages/security_test.yaml",
                "sha256": digest(valid_bytes),
            },
            {
                "source": "payload/two.yaml",
                "target": "packages/security_test.yaml",
                "sha256": digest(second),
            },
        ],
        "Duplicate target",
    ),
    [
        ("payload/one.yaml", valid_bytes),
        ("payload/two.yaml", second),
    ],
)

# 7: excessive compression ratio
bomb = b"A" * (1024 * 1024)
write_zip(
    OUT / "07_compression_ratio.zip",
    manifest(
        [{
            "source": "payload/test.yaml",
            "target": "packages/security_test.yaml",
            "sha256": digest(bomb),
        }],
        "Compression ratio",
    ),
    [("payload/test.yaml", bomb)],
)

print(f"Generated security test packages in {OUT}")
