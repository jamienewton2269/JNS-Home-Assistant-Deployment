#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import argparse
import json


def main() -> int:
    parser = argparse.ArgumentParser(description="Create JNS publishers.json from public keys.")
    parser.add_argument("--public-key", action="append", required=True)
    parser.add_argument(
        "--scope",
        action="append",
        choices=["config", "platform"],
        default=None,
    )
    parser.add_argument("--output", default="publishers.json")
    args = parser.parse_args()

    scopes = sorted(set(args.scope or ["config"]))
    publishers = []
    for item in args.public_key:
        data = json.loads(Path(item).read_text(encoding="utf-8"))
        publishers.append(
            {
                "id": data["id"],
                "name": data.get("name", data["id"]),
                "public_key": data["public_key"],
                "fingerprint_sha256": data["fingerprint_sha256"],
                "scopes": scopes,
                "enabled": True,
            }
        )
    output = Path(args.output)
    output.write_text(
        json.dumps({"schema": 1, "publishers": publishers}, indent=2) + "\n",
        encoding="utf-8",
    )
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
