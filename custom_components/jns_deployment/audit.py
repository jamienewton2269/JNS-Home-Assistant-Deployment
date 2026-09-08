from __future__ import annotations

from pathlib import Path
from typing import Any
import hashlib
import json
import os
import time

from .const import AUDIT_FILE


class AuditError(Exception):
    """Raised when the audit chain cannot be verified."""


class AuditLog:
    GENESIS_HASH = "0" * 64

    def __init__(self, audit_dir: Path) -> None:
        self.audit_dir = audit_dir.resolve()
        self.audit_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.audit_dir / AUDIT_FILE

    @staticmethod
    def _canonical(record: dict[str, Any]) -> bytes:
        return json.dumps(
            record, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")

    @classmethod
    def _record_hash(cls, record_without_hash: dict[str, Any]) -> str:
        return hashlib.sha256(cls._canonical(record_without_hash)).hexdigest()

    def verify(self) -> dict[str, Any]:
        if not self.path.is_file():
            return {
                "ok": True,
                "entries": 0,
                "last_hash": self.GENESIS_HASH,
                "path": str(self.path),
            }
        previous_hash = self.GENESIS_HASH
        expected_seq = 1
        entries = 0
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise AuditError(f"Unable to read audit log: {exc}") from exc
        for line_number, line in enumerate(lines, 1):
            if not line.strip():
                continue
            try:
                full = json.loads(line)
            except json.JSONDecodeError as exc:
                raise AuditError(f"Audit log line {line_number} is invalid JSON.") from exc
            recorded_hash = full.get("hash")
            record = {key: value for key, value in full.items() if key != "hash"}
            if record.get("seq") != expected_seq:
                raise AuditError(f"Audit sequence mismatch at line {line_number}.")
            if record.get("previous_hash") != previous_hash:
                raise AuditError(f"Audit chain mismatch at line {line_number}.")
            actual_hash = self._record_hash(record)
            if recorded_hash != actual_hash:
                raise AuditError(f"Audit record hash mismatch at line {line_number}.")
            previous_hash = actual_hash
            expected_seq += 1
            entries += 1
        return {
            "ok": True,
            "entries": entries,
            "last_hash": previous_hash,
            "path": str(self.path),
        }

    def append(self, event: str, details: dict[str, Any]) -> dict[str, Any]:
        state = self.verify()
        record = {
            "seq": state["entries"] + 1,
            "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "event": event,
            "details": details,
            "previous_hash": state["last_hash"],
        }
        record_hash = self._record_hash(record)
        full = {**record, "hash": record_hash}
        data = (
            json.dumps(full, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            + "\n"
        ).encode("utf-8")
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            os.write(fd, data)
            os.fsync(fd)
        finally:
            os.close(fd)
        return full
