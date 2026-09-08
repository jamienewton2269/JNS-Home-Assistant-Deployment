#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import argparse
import base64
import getpass
import hashlib
import json

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate an offline JNS Ed25519 publisher key.")
    parser.add_argument("--publisher-id", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--out-dir", default="jns_keys")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    private_path = out_dir / f"{args.publisher_id}.private.pem"
    public_path = out_dir / f"{args.publisher_id}.public.json"
    if private_path.exists() or public_path.exists():
        raise SystemExit("Refusing to overwrite an existing publisher key.")

    password = getpass.getpass("Private-key passphrase: ")
    confirm = getpass.getpass("Confirm passphrase: ")
    if not password or password != confirm:
        raise SystemExit("Passphrases do not match or are empty.")

    private_key = Ed25519PrivateKey.generate()
    public_raw = private_key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    fingerprint = hashlib.sha256(public_raw).hexdigest()

    private_path.write_bytes(
        private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.BestAvailableEncryption(password.encode("utf-8")),
        )
    )
    public_path.write_text(
        json.dumps(
            {
                "id": args.publisher_id,
                "name": args.name,
                "algorithm": "ed25519",
                "public_key": base64.b64encode(public_raw).decode("ascii"),
                "fingerprint_sha256": fingerprint,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Private key: {private_path}")
    print(f"Public key:  {public_path}")
    print(f"Fingerprint: {fingerprint}")
    print("Keep the private key OFF Home Assistant.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
