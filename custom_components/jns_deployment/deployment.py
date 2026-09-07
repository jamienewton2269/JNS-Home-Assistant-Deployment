\
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any
import hashlib
import json
import os
import shutil
import stat
import tempfile
import time
import uuid
import zipfile

from .const import (
    PACKAGE_MANIFEST,
    TRANSACTION_RECORD,
    MAX_PACKAGE_BYTES,
    MAX_MEMBER_BYTES,
    MAX_MEMBER_COUNT,
    ALLOWED_ROOTS,
)


class DeploymentError(Exception):
    """Raised when a JNS package fails validation or deployment."""


@dataclass(frozen=True)
class ValidatedFile:
    source_member: str
    target_rel: str
    sha256: str
    size: int


class DeploymentManager:
    def __init__(self, config_root: Path, inbox_rel: str, staging_rel: str, backups_rel: str):
        self.config_root = config_root.resolve()
        self.inbox = (self.config_root / inbox_rel).resolve()
        self.staging = (self.config_root / staging_rel).resolve()
        self.backups = (self.config_root / backups_rel).resolve()
        for path in (self.inbox, self.staging, self.backups):
            path.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _sha256_file(path: Path) -> str:
        h = hashlib.sha256()
        with path.open("rb") as f:
            for block in iter(lambda: f.read(1024 * 1024), b""):
                h.update(block)
        return h.hexdigest()

    @staticmethod
    def _safe_posix_path(value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise DeploymentError("Empty package path is not allowed.")
        if "\\" in value:
            raise DeploymentError(f"Backslashes are not allowed in package paths: {value!r}")
        p = PurePosixPath(value)
        if p.is_absolute() or ".." in p.parts or "." in p.parts:
            raise DeploymentError(f"Unsafe package path: {value!r}")
        normalized = str(p)
        if normalized.startswith("/") or normalized == "":
            raise DeploymentError(f"Unsafe package path: {value!r}")
        return normalized

    @staticmethod
    def _allowed_target(target_rel: str) -> bool:
        return any(target_rel.startswith(prefix) for prefix in ALLOWED_ROOTS)

    def _package_path(self, package_name: str) -> Path:
        if Path(package_name).name != package_name:
            raise DeploymentError("Package must be a file name only, not a path.")
        if not package_name.lower().endswith(".zip"):
            raise DeploymentError("Only .zip JNS deployment packages are accepted.")
        package = (self.inbox / package_name).resolve()
        if package.parent != self.inbox:
            raise DeploymentError("Package path escaped the JNS inbox.")
        if not package.is_file():
            raise DeploymentError(f"Package not found in {self.inbox}: {package_name}")
        if package.stat().st_size > MAX_PACKAGE_BYTES:
            raise DeploymentError("Package exceeds the maximum permitted size.")
        return package

    def _read_manifest(self, zf: zipfile.ZipFile) -> dict[str, Any]:
        try:
            raw = zf.read(PACKAGE_MANIFEST)
        except KeyError as exc:
            raise DeploymentError(f"Package is missing {PACKAGE_MANIFEST}.") from exc
        try:
            manifest = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            raise DeploymentError("Package manifest is not valid UTF-8 JSON.") from exc

        if manifest.get("format") != 1:
            raise DeploymentError("Unsupported JNS package format.")
        if not isinstance(manifest.get("name"), str) or not manifest["name"].strip():
            raise DeploymentError("Manifest requires a package name.")
        if not isinstance(manifest.get("version"), str) or not manifest["version"].strip():
            raise DeploymentError("Manifest requires a package version.")
        if not isinstance(manifest.get("files"), list) or not manifest["files"]:
            raise DeploymentError("Manifest requires a non-empty files list.")
        return manifest

    def _validate_zip_metadata(self, zf: zipfile.ZipFile):
        infos = zf.infolist()
        if len(infos) > MAX_MEMBER_COUNT:
            raise DeploymentError("Package contains too many archive members.")

        seen = set()
        for info in infos:
            name = self._safe_posix_path(info.filename.rstrip("/")) if info.filename.rstrip("/") else None
            if not name:
                continue
            if name in seen:
                raise DeploymentError(f"Duplicate ZIP member: {name}")
            seen.add(name)

            mode = (info.external_attr >> 16) & 0xFFFF
            if mode and stat.S_ISLNK(mode):
                raise DeploymentError(f"Symbolic links are forbidden: {name}")
            if info.file_size > MAX_MEMBER_BYTES:
                raise DeploymentError(f"Archive member exceeds maximum size: {name}")

    def validate_package(self, package_name: str) -> dict[str, Any]:
        package = self._package_path(package_name)
        package_sha256 = self._sha256_file(package)

        with zipfile.ZipFile(package, "r") as zf:
            self._validate_zip_metadata(zf)
            manifest = self._read_manifest(zf)

            validated: list[ValidatedFile] = []
            declared_members = set()
            for entry in manifest["files"]:
                if not isinstance(entry, dict):
                    raise DeploymentError("Each manifest files entry must be an object.")
                member = self._safe_posix_path(entry.get("source", ""))
                target_rel = self._safe_posix_path(entry.get("target", ""))
                expected = str(entry.get("sha256", "")).lower()

                if not self._allowed_target(target_rel):
                    raise DeploymentError(
                        f"Target is outside JNS allowed roots: {target_rel}. "
                        f"Allowed roots: {', '.join(ALLOWED_ROOTS)}"
                    )
                if len(expected) != 64 or any(c not in "0123456789abcdef" for c in expected):
                    raise DeploymentError(f"Invalid SHA-256 in manifest for {member}.")
                if member in declared_members:
                    raise DeploymentError(f"Manifest declares member more than once: {member}")
                declared_members.add(member)

                try:
                    info = zf.getinfo(member)
                except KeyError as exc:
                    raise DeploymentError(f"Manifest member missing from ZIP: {member}") from exc

                if info.is_dir():
                    raise DeploymentError(f"Manifest member must be a file: {member}")

                data = zf.read(member)
                actual = hashlib.sha256(data).hexdigest()
                if actual != expected:
                    raise DeploymentError(
                        f"SHA-256 mismatch for {member}: expected {expected}, got {actual}"
                    )
                validated.append(
                    ValidatedFile(
                        source_member=member,
                        target_rel=target_rel,
                        sha256=actual,
                        size=len(data),
                    )
                )

            allowed_archive_members = declared_members | {PACKAGE_MANIFEST}
            undeclared = []
            for info in zf.infolist():
                if info.is_dir():
                    continue
                normalized = self._safe_posix_path(info.filename)
                if normalized not in allowed_archive_members:
                    undeclared.append(normalized)
            if undeclared:
                raise DeploymentError(
                    "Package contains undeclared files: " + ", ".join(sorted(undeclared))
                )

        return {
            "ok": True,
            "package": package_name,
            "package_sha256": package_sha256,
            "name": manifest["name"],
            "version": manifest["version"],
            "file_count": len(validated),
            "files": [vf.__dict__ for vf in validated],
        }

    def install_package(self, package_name: str, dry_run: bool = False) -> dict[str, Any]:
        validation = self.validate_package(package_name)
        if dry_run:
            return {**validation, "dry_run": True, "installed": False}

        package = self._package_path(package_name)
        txid = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + uuid.uuid4().hex[:10]
        stage_root = (self.staging / txid).resolve()
        backup_root = (self.backups / txid).resolve()
        stage_root.mkdir(parents=True, exist_ok=False)
        backup_root.mkdir(parents=True, exist_ok=False)

        transaction = {
            "transaction_id": txid,
            "package": package_name,
            "package_sha256": validation["package_sha256"],
            "name": validation["name"],
            "version": validation["version"],
            "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "files": [],
            "status": "staging",
        }

        try:
            with zipfile.ZipFile(package, "r") as zf:
                manifest = self._read_manifest(zf)

                # Stage every file first. Nothing is written to live config yet.
                for entry in manifest["files"]:
                    member = self._safe_posix_path(entry["source"])
                    target_rel = self._safe_posix_path(entry["target"])
                    staged = (stage_root / target_rel).resolve()
                    if stage_root not in staged.parents:
                        raise DeploymentError(f"Staged path escaped transaction root: {target_rel}")
                    staged.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(member, "r") as src, staged.open("wb") as dst:
                        shutil.copyfileobj(src, dst)

                    actual = self._sha256_file(staged)
                    if actual != entry["sha256"].lower():
                        raise DeploymentError(f"Staged hash mismatch for {target_rel}")

                # Commit with backups.
                transaction["status"] = "committing"
                for entry in manifest["files"]:
                    target_rel = self._safe_posix_path(entry["target"])
                    live = (self.config_root / target_rel).resolve()
                    if self.config_root not in live.parents:
                        raise DeploymentError(f"Live path escaped Home Assistant config: {target_rel}")

                    staged = (stage_root / target_rel).resolve()
                    backup = (backup_root / target_rel).resolve()
                    existed = live.exists()

                    if existed:
                        if live.is_symlink():
                            raise DeploymentError(f"Refusing to overwrite symbolic link: {target_rel}")
                        if live.is_dir():
                            raise DeploymentError(f"Refusing to overwrite directory with file: {target_rel}")
                        backup.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(live, backup)

                    live.parent.mkdir(parents=True, exist_ok=True)
                    tx_item = {
                        "target": target_rel,
                        "previously_existed": existed,
                        "installed_sha256": None,
                    }
                    transaction["files"].append(tx_item)

                    fd, tmp_name = tempfile.mkstemp(prefix=".jns-", dir=str(live.parent))
                    os.close(fd)
                    tmp = Path(tmp_name)
                    try:
                        shutil.copy2(staged, tmp)
                        os.replace(tmp, live)
                    finally:
                        if tmp.exists():
                            tmp.unlink(missing_ok=True)

                    tx_item["installed_sha256"] = self._sha256_file(live)

            transaction["status"] = "committed"
            (backup_root / TRANSACTION_RECORD).write_text(
                json.dumps(transaction, indent=2), encoding="utf-8"
            )
            return {
                "ok": True,
                "installed": True,
                "dry_run": False,
                "transaction_id": txid,
                "package": package_name,
                "name": validation["name"],
                "version": validation["version"],
                "file_count": len(transaction["files"]),
            }

        except Exception:
            # Best-effort rollback if commit partially occurred.
            try:
                for item in reversed(transaction["files"]):
                    target_rel = item["target"]
                    live = (self.config_root / target_rel).resolve()
                    backup = (backup_root / target_rel).resolve()
                    if item["previously_existed"] and backup.is_file():
                        live.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(backup, live)
                    elif not item["previously_existed"] and live.is_file():
                        live.unlink()
                transaction["status"] = "rolled_back_after_failure"
                (backup_root / TRANSACTION_RECORD).write_text(
                    json.dumps(transaction, indent=2), encoding="utf-8"
                )
            finally:
                shutil.rmtree(stage_root, ignore_errors=True)
            raise
        finally:
            shutil.rmtree(stage_root, ignore_errors=True)

    def rollback_transaction(self, transaction_id: str) -> dict[str, Any]:
        if Path(transaction_id).name != transaction_id:
            raise DeploymentError("Invalid transaction id.")
        txroot = (self.backups / transaction_id).resolve()
        if txroot.parent != self.backups or not txroot.is_dir():
            raise DeploymentError("Transaction backup not found.")

        record_path = txroot / TRANSACTION_RECORD
        if not record_path.is_file():
            raise DeploymentError("Transaction record is missing.")

        record = json.loads(record_path.read_text(encoding="utf-8"))
        files = record.get("files", [])
        if not isinstance(files, list):
            raise DeploymentError("Transaction record is invalid.")

        restored = []
        for item in reversed(files):
            target_rel = self._safe_posix_path(item["target"])
            live = (self.config_root / target_rel).resolve()
            if self.config_root not in live.parents:
                raise DeploymentError(f"Rollback target escaped config root: {target_rel}")
            backup = (txroot / target_rel).resolve()

            if item.get("previously_existed"):
                if not backup.is_file():
                    raise DeploymentError(f"Required rollback file is missing: {target_rel}")
                live.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(backup, live)
            else:
                if live.is_file():
                    live.unlink()
            restored.append(target_rel)

        record["status"] = "rolled_back"
        record["rolled_back_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        record_path.write_text(json.dumps(record, indent=2), encoding="utf-8")

        return {
            "ok": True,
            "transaction_id": transaction_id,
            "restored_count": len(restored),
            "restored": restored,
        }
