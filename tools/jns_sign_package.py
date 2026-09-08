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
    parser = argparse.ArgumentParser(description="Sign an existing JNS ZIP as production format 3.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--private-key", required=True)
    parser.add_argument("--publisher-id", required=True)
    parser.add_argument(
        "--type",
        choices=["config_package", "platform_update"],
        default="config_package",
    )
    parser.add_argument("--package-id")
    parser.add_argument("--from-version", action="append")
    parser.add_argument("--to-version")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    with zipfile.ZipFile(input_path, "r") as source:
        old_manifest = json.loads(source.read("jns_package.json").decode("utf-8"))
        files = old_manifest.get("files")
        if not isinstance(files, list) or not files:
            raise SystemExit("Input package has no declared files.")
        manifest = {
            "format": 3,
            "type": args.type,
            "publisher_id": args.publisher_id,
            "package_id": args.package_id or old_manifest.get("package_id") or "signed_package",
            "name": old_manifest["name"],
            "version": old_manifest["version"],
        }
        if args.type == "platform_update":
            if not args.to_version:
                raise SystemExit("--to-version is required for platform_update")
            manifest.update(
                {
                    "domain": "jns_deployment",
                    "from_version": args.from_version or ["*"],
                    "to_version": args.to_version,
                }
            )
        manifest["files"] = files
        raw_manifest = (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode("utf-8")

        password = getpass.getpass("Private-key passphrase: ")
        private_key = serialization.load_pem_private_key(
            Path(args.private_key).read_bytes(),
            password=password.encode("utf-8"),
        )
        signature_bytes = private_key.sign(SIGNATURE_DOMAIN + raw_manifest)
        signature = {
            "algorithm": "ed25519",
            "publisher_id": args.publisher_id,
            "manifest_sha256": hashlib.sha256(raw_manifest).hexdigest(),
            "signature": base64.b64encode(signature_bytes).decode("ascii"),
        }
        declared_sources = [entry["source"] for entry in files]
        for source_name in declared_sources:
            source.getinfo(source_name)

        with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as target:
            target.writestr("jns_package.json", raw_manifest)
            target.writestr("jns_signature.json", json.dumps(signature, indent=2) + "\n")
            for source_name in declared_sources:
                target.writestr(source_name, source.read(source_name))

    print(output_path)
    print("SHA-256:", hashlib.sha256(output_path.read_bytes()).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
