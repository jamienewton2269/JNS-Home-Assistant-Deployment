#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import argparse
import base64
import getpass
import hashlib
import json
import zipfile

from cryptography.hazmat.primitives import serialization

SIGNATURE_DOMAIN = b"JNS-PACKAGE-V3\x00"


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a signed JNS platform update.")
    parser.add_argument("--repo", default=".")
    parser.add_argument("--private-key", required=True)
    parser.add_argument("--publisher-id", required=True)
    parser.add_argument("--from-version", action="append", required=True)
    parser.add_argument("--to-version", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    integration = repo / "custom_components" / "jns_deployment"
    if not integration.is_dir():
        raise SystemExit("JNS integration directory not found.")
    files = []
    members = []
    for path in sorted(integration.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        relative = path.relative_to(integration).as_posix()
        source_name = f"payload/jns_deployment/{relative}"
        target_name = f"custom_components/jns_deployment/{relative}"
        data = path.read_bytes()
        files.append(
            {
                "source": source_name,
                "target": target_name,
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        )
        members.append((source_name, data))
    manifest = {
        "format": 3,
        "type": "platform_update",
        "publisher_id": args.publisher_id,
        "package_id": "jns_platform",
        "domain": "jns_deployment",
        "name": f"JNS Platform Update {args.to_version}",
        "version": args.to_version,
        "from_version": args.from_version,
        "to_version": args.to_version,
        "files": files,
    }
    raw_manifest = (json.dumps(manifest, indent=2) + "\n").encode("utf-8")
    password = getpass.getpass("Private-key passphrase: ")
    private_key = serialization.load_pem_private_key(
        Path(args.private_key).read_bytes(), password=password.encode("utf-8")
    )
    signature_bytes = private_key.sign(SIGNATURE_DOMAIN + raw_manifest)
    signature = {
        "algorithm": "ed25519",
        "publisher_id": args.publisher_id,
        "manifest_sha256": hashlib.sha256(raw_manifest).hexdigest(),
        "signature": base64.b64encode(signature_bytes).decode("ascii"),
    }
    output = Path(args.output)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("jns_package.json", raw_manifest)
        archive.writestr("jns_signature.json", json.dumps(signature, indent=2) + "\n")
        for name, data in members:
            archive.writestr(name, data)
    print(output)
    print("SHA-256:", hashlib.sha256(output.read_bytes()).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
