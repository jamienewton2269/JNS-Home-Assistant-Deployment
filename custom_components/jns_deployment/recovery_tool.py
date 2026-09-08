#!/usr/bin/env python3
"""Standalone JNS emergency transaction recovery tool."""

from __future__ import annotations

from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import sys


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def restore_platform(config: Path, tx_root: Path) -> None:
    backup = tx_root / "platform_backup" / "jns_deployment"
    live = config / "custom_components" / "jns_deployment"
    hold = config / "custom_components" / ".jns_emergency_hold"
    if not backup.is_dir():
        raise RuntimeError("Platform backup tree is missing.")
    if hold.exists():
        shutil.rmtree(hold)
    if live.exists():
        os.replace(live, hold)
    try:
        shutil.copytree(backup, live)
    except Exception:
        if not live.exists() and hold.exists():
            os.replace(hold, live)
        raise
    shutil.rmtree(hold, ignore_errors=True)


def restore_normal(config: Path, tx_root: Path, record: dict) -> None:
    for item in reversed(record.get("files", [])):
        if item.get("action") == "unchanged":
            continue
        target = config / item["target"]
        if item.get("previously_existed"):
            backup = tx_root / item["target"]
            if not backup.is_file():
                raise RuntimeError(f"Required backup missing: {item['target']}")
            expected = item.get("backup_sha256")
            if expected and sha256_file(backup) != expected:
                raise RuntimeError(f"Backup hash mismatch: {item['target']}")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup, target)
        elif target.is_file():
            target.unlink()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="/config")
    parser.add_argument("--transaction", required=True)
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args()

    config = Path(args.config).resolve()
    tx_root = (config / "jns" / "backups" / args.transaction).resolve()
    record_path = tx_root / "transaction.json"
    if not record_path.is_file():
        print("Transaction record not found.", file=sys.stderr)
        return 2
    record = json.loads(record_path.read_text(encoding="utf-8"))
    print(
        f"Transaction: {args.transaction}\n"
        f"Kind: {record.get('kind')}\n"
        f"Status: {record.get('status')}"
    )
    if not args.yes:
        if input("Type RESTORE to restore the pre-transaction state: ") != "RESTORE":
            print("Cancelled.")
            return 1
    if record.get("kind") == "platform_update":
        restore_platform(config, tx_root)
    elif record.get("kind") == "package_install":
        restore_normal(config, tx_root, record)
    else:
        print("Unsupported transaction kind.", file=sys.stderr)
        return 2
    record["status"] = "emergency_recovered"
    record_path.write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print("Recovery completed. Restart Home Assistant.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
