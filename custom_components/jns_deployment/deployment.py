from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterator
import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
import threading
import time
import uuid
import zipfile

from .const import (
    ALLOWED_EXTENSIONS,
    ALLOWED_ROOTS,
    FORMAT_CONFIG_PACKAGE,
    FORMAT_PLATFORM_UPDATE,
    MAX_COMPRESSION_RATIO,
    MAX_MEMBER_BYTES,
    MAX_MEMBER_COUNT,
    MAX_PACKAGE_BYTES,
    MAX_TOTAL_UNCOMPRESSED_BYTES,
    PACKAGE_MANIFEST,
    PENDING_PLATFORM_UPDATE,
    PLATFORM_DOMAIN,
    PLATFORM_REQUIRED_TARGETS,
    PLATFORM_TARGET_ROOT,
    TRANSACTION_RECORD,
)


class DeploymentError(Exception):
    """Expected JNS validation, policy, transaction, or rollback failure."""


@dataclass(frozen=True)
class ValidatedFile:
    source_member: str
    target_rel: str
    sha256: str
    size: int


class DeploymentManager:
    """JNS configuration deployment and trusted-hash platform updater."""

    def __init__(
        self,
        config_root: Path,
        inbox_rel: str,
        staging_rel: str,
        backups_rel: str,
        state_rel: str,
        platform_updates_rel: str,
    ) -> None:
        self.config_root = config_root.resolve()
        self.inbox = (self.config_root / inbox_rel).resolve()
        self.staging = (self.config_root / staging_rel).resolve()
        self.backups = (self.config_root / backups_rel).resolve()
        self.state = (self.config_root / state_rel).resolve()
        self.platform_updates = (
            self.config_root / platform_updates_rel
        ).resolve()
        self._operation_lock = threading.Lock()

        for path in (
            self.inbox,
            self.staging,
            self.backups,
            self.state,
            self.platform_updates,
        ):
            path.mkdir(parents=True, exist_ok=True)

        self._mark_interrupted_transactions()

    # ------------------------------------------------------------------
    # Generic helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _sha256_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as file_handle:
            for block in iter(lambda: file_handle.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    @staticmethod
    def _valid_sha256(value: str) -> bool:
        return (
            isinstance(value, str)
            and len(value) == 64
            and all(char in "0123456789abcdefABCDEF" for char in value)
        )

    @staticmethod
    def _write_json_atomic(path: Path, data: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(
            prefix=".jns-json-",
            dir=str(path.parent),
        )
        os.close(fd)
        temp_path = Path(temp_name)
        try:
            temp_path.write_text(
                json.dumps(data, indent=2) + "\n",
                encoding="utf-8",
            )
            os.replace(temp_path, path)
        finally:
            temp_path.unlink(missing_ok=True)

    @staticmethod
    def _safe_posix_path(value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise DeploymentError("Empty package path is not allowed.")
        if "\x00" in value:
            raise DeploymentError("NUL bytes are not allowed in package paths.")
        if "\\" in value:
            raise DeploymentError(
                f"Backslashes are not allowed in package paths: {value!r}"
            )

        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts or "." in path.parts:
            raise DeploymentError(f"Unsafe package path: {value!r}")

        normalized = str(path)
        if not normalized or normalized.startswith("/"):
            raise DeploymentError(f"Unsafe package path: {value!r}")
        return normalized

    @staticmethod
    def _package_id(manifest: dict[str, Any]) -> str:
        explicit = manifest.get("package_id")
        if isinstance(explicit, str) and explicit.strip():
            package_id = explicit.strip().lower()
        else:
            package_id = re.sub(
                r"[^a-z0-9]+",
                "_",
                str(manifest["name"]).lower(),
            ).strip("_")

        if not package_id or len(package_id) > 80:
            raise DeploymentError("Package id is empty or too long.")
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", package_id):
            raise DeploymentError(
                "Package id may contain lowercase letters, digits, '_' and '-'."
            )
        return package_id

    @contextmanager
    def _exclusive_operation(self) -> Iterator[None]:
        if not self._operation_lock.acquire(blocking=False):
            raise DeploymentError(
                "Another JNS deployment, recovery, or rollback is already in progress."
            )
        try:
            yield
        finally:
            self._operation_lock.release()

    def _transaction_path(self, transaction_id: str) -> Path:
        if Path(transaction_id).name != transaction_id:
            raise DeploymentError("Invalid transaction id.")
        root = (self.backups / transaction_id).resolve()
        if root.parent != self.backups:
            raise DeploymentError("Transaction path escaped backup root.")
        return root / TRANSACTION_RECORD

    def _read_transaction(self, transaction_id: str) -> dict[str, Any]:
        record_path = self._transaction_path(transaction_id)
        if not record_path.is_file():
            raise DeploymentError("Transaction record not found.")
        try:
            return json.loads(record_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise DeploymentError(
                "Transaction record is not valid JSON."
            ) from exc

    def _mark_interrupted_transactions(self) -> None:
        for directory in self.backups.iterdir():
            if not directory.is_dir():
                continue
            record_path = directory / TRANSACTION_RECORD
            if not record_path.is_file():
                continue
            try:
                record = json.loads(record_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue

            if record.get("status") in {"staging", "committing"}:
                record["status"] = "interrupted"
                record["interrupted_detected_utc"] = time.strftime(
                    "%Y-%m-%dT%H:%M:%SZ",
                    time.gmtime(),
                )
                self._write_json_atomic(record_path, record)

    # ------------------------------------------------------------------
    # ZIP validation
    # ------------------------------------------------------------------

    def _archive_path(
        self,
        root: Path,
        package_name: str,
    ) -> Path:
        if Path(package_name).name != package_name:
            raise DeploymentError(
                "Package must be a filename only, not a filesystem path."
            )
        if not package_name.lower().endswith(".zip"):
            raise DeploymentError("Only ZIP packages are accepted.")

        package = (root / package_name).resolve()
        if package.parent != root:
            raise DeploymentError("Package path escaped its JNS inbox.")
        if not package.is_file():
            raise DeploymentError(
                f"Package not found in {root}: {package_name}"
            )
        if package.stat().st_size > MAX_PACKAGE_BYTES:
            raise DeploymentError(
                "Package exceeds the maximum permitted compressed size."
            )
        return package

    def _open_archive(self, path: Path) -> zipfile.ZipFile:
        try:
            return zipfile.ZipFile(path, "r")
        except zipfile.BadZipFile as exc:
            raise DeploymentError("Package is not a valid ZIP archive.") from exc

    def _read_manifest(
        self,
        archive: zipfile.ZipFile,
        expected_format: int,
    ) -> dict[str, Any]:
        try:
            raw = archive.read(PACKAGE_MANIFEST)
        except KeyError as exc:
            raise DeploymentError(
                f"Package is missing {PACKAGE_MANIFEST}."
            ) from exc

        try:
            manifest = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise DeploymentError(
                "Package manifest is not valid UTF-8 JSON."
            ) from exc

        if manifest.get("format") != expected_format:
            raise DeploymentError(
                f"Expected JNS package format {expected_format}."
            )
        if not isinstance(manifest.get("name"), str) or not manifest["name"].strip():
            raise DeploymentError("Manifest requires a package name.")
        if not isinstance(manifest.get("version"), str) or not manifest["version"].strip():
            raise DeploymentError("Manifest requires a package version.")
        if not isinstance(manifest.get("files"), list) or not manifest["files"]:
            raise DeploymentError("Manifest requires a non-empty files list.")
        return manifest

    def _validate_zip_metadata(self, archive: zipfile.ZipFile) -> None:
        infos = archive.infolist()
        if len(infos) > MAX_MEMBER_COUNT:
            raise DeploymentError("Package contains too many archive members.")

        seen: set[str] = set()
        total_uncompressed = 0

        for info in infos:
            stripped = info.filename.rstrip("/")
            if not stripped:
                continue

            name = self._safe_posix_path(stripped)
            if name in seen:
                raise DeploymentError(f"Duplicate ZIP member: {name}")
            seen.add(name)

            if info.flag_bits & 0x1:
                raise DeploymentError(
                    f"Encrypted ZIP members are not permitted: {name}"
                )

            mode = (info.external_attr >> 16) & 0xFFFF
            if mode:
                file_type = stat.S_IFMT(mode)
                if file_type not in (0, stat.S_IFREG, stat.S_IFDIR):
                    raise DeploymentError(
                        f"Special files are forbidden in packages: {name}"
                    )

            if info.file_size > MAX_MEMBER_BYTES:
                raise DeploymentError(
                    f"Archive member exceeds maximum size: {name}"
                )

            total_uncompressed += info.file_size
            if total_uncompressed > MAX_TOTAL_UNCOMPRESSED_BYTES:
                raise DeploymentError(
                    "Package exceeds the maximum total uncompressed size."
                )

            if info.file_size and info.compress_size:
                ratio = info.file_size / info.compress_size
                if ratio > MAX_COMPRESSION_RATIO:
                    raise DeploymentError(
                        f"Archive member compression ratio is too high: {name}"
                    )

    # ------------------------------------------------------------------
    # Normal configuration packages
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_target_policy(target: str) -> None:
        for prefix, extensions in ALLOWED_EXTENSIONS.items():
            if target.startswith(prefix):
                suffix = PurePosixPath(target).suffix.lower()
                if suffix not in extensions:
                    raise DeploymentError(
                        f"Target file type is not permitted under {prefix}: {target}"
                    )
                return

        raise DeploymentError(
            f"Target is outside JNS allowed roots: {target}. "
            f"Allowed roots: {', '.join(ALLOWED_ROOTS)}"
        )

    def validate_package(self, package_name: str) -> dict[str, Any]:
        package = self._archive_path(self.inbox, package_name)
        package_sha256 = self._sha256_file(package)

        with self._open_archive(package) as archive:
            self._validate_zip_metadata(archive)
            manifest = self._read_manifest(
                archive,
                FORMAT_CONFIG_PACKAGE,
            )
            package_id = self._package_id(manifest)

            validated: list[ValidatedFile] = []
            declared_members: set[str] = set()
            declared_targets: set[str] = set()

            for entry in manifest["files"]:
                if not isinstance(entry, dict):
                    raise DeploymentError(
                        "Each manifest files entry must be an object."
                    )

                member = self._safe_posix_path(entry.get("source", ""))
                target = self._safe_posix_path(entry.get("target", ""))
                expected = str(entry.get("sha256", "")).lower()

                if member == PACKAGE_MANIFEST:
                    raise DeploymentError(
                        "The package manifest cannot also be a payload file."
                    )

                self._validate_target_policy(target)

                if not self._valid_sha256(expected):
                    raise DeploymentError(
                        f"Invalid SHA-256 in manifest for {member}."
                    )

                if member in declared_members:
                    raise DeploymentError(
                        f"Manifest declares member more than once: {member}"
                    )
                declared_members.add(member)

                if target in declared_targets:
                    raise DeploymentError(
                        f"Manifest declares target more than once: {target}"
                    )
                declared_targets.add(target)

                try:
                    info = archive.getinfo(member)
                except KeyError as exc:
                    raise DeploymentError(
                        f"Manifest member missing from ZIP: {member}"
                    ) from exc

                if info.is_dir():
                    raise DeploymentError(
                        f"Manifest member must be a file: {member}"
                    )

                data = archive.read(member)
                actual = hashlib.sha256(data).hexdigest()
                if actual != expected:
                    raise DeploymentError(
                        f"SHA-256 mismatch for {member}: "
                        f"expected {expected}, got {actual}"
                    )

                validated.append(
                    ValidatedFile(
                        source_member=member,
                        target_rel=target,
                        sha256=actual,
                        size=len(data),
                    )
                )

            allowed_archive_members = declared_members | {PACKAGE_MANIFEST}
            undeclared: list[str] = []
            for info in archive.infolist():
                if info.is_dir():
                    continue
                normalized = self._safe_posix_path(info.filename)
                if normalized not in allowed_archive_members:
                    undeclared.append(normalized)

            if undeclared:
                raise DeploymentError(
                    "Package contains undeclared files: "
                    + ", ".join(sorted(undeclared))
                )

        return {
            "ok": True,
            "kind": "config_package",
            "package": package_name,
            "package_id": package_id,
            "package_sha256": package_sha256,
            "name": manifest["name"],
            "version": manifest["version"],
            "file_count": len(validated),
            "files": [asdict(item) for item in validated],
        }

    def plan_package(self, package_name: str) -> dict[str, Any]:
        validation = self.validate_package(package_name)
        changes: list[dict[str, Any]] = []

        for item in validation["files"]:
            target = item["target_rel"]
            live = (self.config_root / target).resolve()
            if self.config_root not in live.parents:
                raise DeploymentError(
                    f"Target escaped Home Assistant config root: {target}"
                )

            if live.is_symlink():
                action = "blocked_symlink"
                current_hash = None
            elif live.is_dir():
                action = "blocked_directory"
                current_hash = None
            elif live.is_file():
                current_hash = self._sha256_file(live)
                action = (
                    "unchanged"
                    if current_hash == item["sha256"]
                    else "replace"
                )
            else:
                current_hash = None
                action = "create"

            changes.append(
                {
                    "target": target,
                    "action": action,
                    "current_sha256": current_hash,
                    "new_sha256": item["sha256"],
                    "size": item["size"],
                }
            )

        return {
            **validation,
            "changes": changes,
            "change_count": sum(
                1
                for item in changes
                if item["action"] in {"create", "replace"}
            ),
            "blocked_count": sum(
                1
                for item in changes
                if item["action"].startswith("blocked_")
            ),
        }

    def install_package(
        self,
        package_name: str,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        with self._exclusive_operation():
            plan = self.plan_package(package_name)

            if plan["blocked_count"]:
                raise DeploymentError(
                    "Deployment plan contains blocked target paths."
                )

            if dry_run:
                return {
                    **plan,
                    "dry_run": True,
                    "installed": False,
                }

            package = self._archive_path(self.inbox, package_name)
            transaction_id = (
                time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
                + "-"
                + uuid.uuid4().hex[:10]
            )
            stage_root = (self.staging / transaction_id).resolve()
            backup_root = (self.backups / transaction_id).resolve()
            transaction_path = backup_root / TRANSACTION_RECORD

            stage_root.mkdir(parents=True, exist_ok=False)
            backup_root.mkdir(parents=True, exist_ok=False)

            transaction: dict[str, Any] = {
                "transaction_id": transaction_id,
                "kind": "package_install",
                "package": package_name,
                "package_id": plan["package_id"],
                "package_sha256": plan["package_sha256"],
                "name": plan["name"],
                "version": plan["version"],
                "created_utc": time.strftime(
                    "%Y-%m-%dT%H:%M:%SZ",
                    time.gmtime(),
                ),
                "files": [],
                "status": "staging",
            }
            self._write_json_atomic(transaction_path, transaction)

            try:
                with self._open_archive(package) as archive:
                    manifest = self._read_manifest(
                        archive,
                        FORMAT_CONFIG_PACKAGE,
                    )

                    # Stage every declared file and verify it again.
                    for entry in manifest["files"]:
                        member = self._safe_posix_path(entry["source"])
                        target = self._safe_posix_path(entry["target"])
                        staged = (stage_root / target).resolve()

                        if stage_root not in staged.parents:
                            raise DeploymentError(
                                f"Staged path escaped transaction root: {target}"
                            )

                        staged.parent.mkdir(parents=True, exist_ok=True)
                        with archive.open(member, "r") as source, staged.open(
                            "wb"
                        ) as destination:
                            shutil.copyfileobj(source, destination)

                        staged_hash = self._sha256_file(staged)
                        if staged_hash != entry["sha256"].lower():
                            raise DeploymentError(
                                f"Staged hash mismatch for {target}"
                            )

                    transaction["status"] = "committing"
                    self._write_json_atomic(transaction_path, transaction)

                    for entry in manifest["files"]:
                        target = self._safe_posix_path(entry["target"])
                        live = (self.config_root / target).resolve()
                        staged = (stage_root / target).resolve()
                        backup = (backup_root / target).resolve()
                        expected_hash = entry["sha256"].lower()

                        if self.config_root not in live.parents:
                            raise DeploymentError(
                                f"Live path escaped Home Assistant config: {target}"
                            )

                        existed = live.exists()
                        current_hash = (
                            self._sha256_file(live)
                            if live.is_file()
                            else None
                        )

                        if live.is_symlink():
                            raise DeploymentError(
                                f"Refusing to overwrite symbolic link: {target}"
                            )
                        if live.is_dir():
                            raise DeploymentError(
                                f"Refusing to overwrite directory with file: {target}"
                            )

                        # Identical files require no live write and no backup.
                        if existed and current_hash == expected_hash:
                            item = {
                                "target": target,
                                "action": "unchanged",
                                "previously_existed": True,
                                "backup_sha256": None,
                                "installed_sha256": expected_hash,
                            }
                            transaction["files"].append(item)
                            self._write_json_atomic(
                                transaction_path,
                                transaction,
                            )
                            continue

                        backup_sha256: str | None = None
                        if existed:
                            backup.parent.mkdir(
                                parents=True,
                                exist_ok=True,
                            )
                            shutil.copy2(live, backup)
                            backup_sha256 = self._sha256_file(backup)

                        item = {
                            "target": target,
                            "action": "replace" if existed else "create",
                            "previously_existed": existed,
                            "backup_sha256": backup_sha256,
                            "installed_sha256": None,
                        }
                        transaction["files"].append(item)

                        # Persist rollback intent before touching live data.
                        self._write_json_atomic(
                            transaction_path,
                            transaction,
                        )

                        live.parent.mkdir(parents=True, exist_ok=True)
                        fd, temp_name = tempfile.mkstemp(
                            prefix=".jns-",
                            dir=str(live.parent),
                        )
                        os.close(fd)
                        temp_path = Path(temp_name)
                        try:
                            shutil.copy2(staged, temp_path)
                            os.replace(temp_path, live)
                        finally:
                            temp_path.unlink(missing_ok=True)

                        installed_hash = self._sha256_file(live)
                        if installed_hash != expected_hash:
                            raise DeploymentError(
                                f"Post-commit hash mismatch for {target}"
                            )

                        item["installed_sha256"] = installed_hash
                        self._write_json_atomic(
                            transaction_path,
                            transaction,
                        )

                transaction["status"] = "committed"
                transaction["committed_utc"] = time.strftime(
                    "%Y-%m-%dT%H:%M:%SZ",
                    time.gmtime(),
                )
                self._write_json_atomic(transaction_path, transaction)

                return {
                    "ok": True,
                    "kind": "package_install",
                    "installed": True,
                    "dry_run": False,
                    "transaction_id": transaction_id,
                    "package": package_name,
                    "package_id": plan["package_id"],
                    "name": plan["name"],
                    "version": plan["version"],
                    "file_count": len(transaction["files"]),
                    "changed_count": sum(
                        1
                        for item in transaction["files"]
                        if item["action"] != "unchanged"
                    ),
                }

            except Exception:
                self._rollback_partial_install(
                    transaction,
                    backup_root,
                )
                self._write_json_atomic(transaction_path, transaction)
                raise
            finally:
                shutil.rmtree(stage_root, ignore_errors=True)

    def _rollback_partial_install(
        self,
        transaction: dict[str, Any],
        backup_root: Path,
    ) -> None:
        rollback_errors: list[str] = []

        for item in reversed(transaction.get("files", [])):
            if item.get("action") == "unchanged":
                continue

            target = item["target"]
            live = (self.config_root / target).resolve()
            backup = (backup_root / target).resolve()

            try:
                if item["previously_existed"] and backup.is_file():
                    live.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(backup, live)
                elif (
                    not item["previously_existed"]
                    and live.is_file()
                ):
                    live.unlink()
            except OSError as exc:
                rollback_errors.append(f"{target}: {exc}")

        transaction["status"] = (
            "rollback_failed_after_install_failure"
            if rollback_errors
            else "rolled_back_after_failure"
        )
        if rollback_errors:
            transaction["rollback_errors"] = rollback_errors

    def rollback_transaction(
        self,
        transaction_id: str,
        force: bool = False,
    ) -> dict[str, Any]:
        with self._exclusive_operation():
            record = self._read_transaction(transaction_id)

            if record.get("kind") != "package_install":
                raise DeploymentError(
                    "This transaction is not a normal package installation."
                )
            if record.get("status") == "rolled_back":
                raise DeploymentError("Transaction is already rolled back.")
            if record.get("status") != "committed":
                raise DeploymentError(
                    f"Transaction cannot be rolled back from status "
                    f"{record.get('status')!r}; use interrupted recovery if needed."
                )

            transaction_root = self._transaction_path(
                transaction_id
            ).parent
            files = record.get("files", [])
            if not isinstance(files, list):
                raise DeploymentError("Transaction record is invalid.")

            # Preflight all files before changing any live data.
            for item in files:
                if item.get("action") == "unchanged":
                    continue

                target = self._safe_posix_path(item["target"])
                live = (self.config_root / target).resolve()
                if self.config_root not in live.parents:
                    raise DeploymentError(
                        f"Rollback target escaped config root: {target}"
                    )

                installed_hash = item.get("installed_sha256")
                if live.is_file() and installed_hash and not force:
                    current_hash = self._sha256_file(live)
                    if current_hash != installed_hash:
                        raise DeploymentError(
                            f"Refusing rollback because {target} changed "
                            "after deployment. Use force only after reviewing "
                            "the changed file."
                        )

                if item.get("previously_existed"):
                    backup = (transaction_root / target).resolve()
                    if not backup.is_file():
                        raise DeploymentError(
                            f"Required rollback file is missing: {target}"
                        )
                    expected_backup_hash = item.get("backup_sha256")
                    if expected_backup_hash:
                        actual_backup_hash = self._sha256_file(backup)
                        if actual_backup_hash != expected_backup_hash:
                            raise DeploymentError(
                                f"Rollback backup hash mismatch for {target}"
                            )

            restored: list[str] = []
            for item in reversed(files):
                if item.get("action") == "unchanged":
                    continue

                target = self._safe_posix_path(item["target"])
                live = (self.config_root / target).resolve()
                backup = (transaction_root / target).resolve()

                if item.get("previously_existed"):
                    live.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(backup, live)
                elif live.is_file():
                    live.unlink()

                restored.append(target)

            record["status"] = "rolled_back"
            record["rolled_back_utc"] = time.strftime(
                "%Y-%m-%dT%H:%M:%SZ",
                time.gmtime(),
            )
            record["rollback_forced"] = bool(force)
            self._write_json_atomic(
                self._transaction_path(transaction_id),
                record,
            )

            return {
                "ok": True,
                "transaction_id": transaction_id,
                "restored_count": len(restored),
                "restored": restored,
                "forced": bool(force),
            }

    # ------------------------------------------------------------------
    # Interrupted transaction recovery
    # ------------------------------------------------------------------

    def recover_interrupted_transaction(
        self,
        transaction_id: str,
    ) -> dict[str, Any]:
        with self._exclusive_operation():
            record = self._read_transaction(transaction_id)

            if record.get("kind") != "package_install":
                raise DeploymentError(
                    "Only interrupted normal package transactions are "
                    "recoverable with this action."
                )
            if record.get("status") != "interrupted":
                raise DeploymentError(
                    "Transaction is not marked as interrupted."
                )

            transaction_root = self._transaction_path(
                transaction_id
            ).parent
            restored: list[str] = []

            # Explicit recovery means returning to the pre-transaction state.
            for item in reversed(record.get("files", [])):
                if item.get("action") == "unchanged":
                    continue

                target = self._safe_posix_path(item["target"])
                live = (self.config_root / target).resolve()
                backup = (transaction_root / target).resolve()

                if item.get("previously_existed"):
                    if not backup.is_file():
                        raise DeploymentError(
                            f"Interrupted transaction backup missing: {target}"
                        )
                    expected = item.get("backup_sha256")
                    if expected and self._sha256_file(backup) != expected:
                        raise DeploymentError(
                            f"Interrupted transaction backup hash mismatch: {target}"
                        )
                    live.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(backup, live)
                elif live.is_file():
                    live.unlink()

                restored.append(target)

            record["status"] = "recovered"
            record["recovered_utc"] = time.strftime(
                "%Y-%m-%dT%H:%M:%SZ",
                time.gmtime(),
            )
            self._write_json_atomic(
                self._transaction_path(transaction_id),
                record,
            )

            return {
                "ok": True,
                "transaction_id": transaction_id,
                "status": "recovered",
                "restored": restored,
            }

    # ------------------------------------------------------------------
    # Package / transaction inventory
    # ------------------------------------------------------------------

    def list_inbox_packages(self) -> dict[str, Any]:
        packages: list[dict[str, Any]] = []

        for path in sorted(self.inbox.glob("*.zip")):
            item: dict[str, Any] = {
                "package": path.name,
                "size": path.stat().st_size,
                "sha256": self._sha256_file(path),
            }
            try:
                validation = self.validate_package(path.name)
            except DeploymentError as exc:
                item["valid"] = False
                item["error"] = str(exc)
            else:
                item.update(
                    {
                        "valid": True,
                        "package_id": validation["package_id"],
                        "name": validation["name"],
                        "version": validation["version"],
                        "file_count": validation["file_count"],
                    }
                )
            packages.append(item)

        return {
            "count": len(packages),
            "packages": packages,
        }

    def list_transactions(self, limit: int = 50) -> dict[str, Any]:
        limit = max(1, min(int(limit), 100))
        transactions: list[dict[str, Any]] = []

        for directory in sorted(
            (path for path in self.backups.iterdir() if path.is_dir()),
            key=lambda path: path.name,
            reverse=True,
        ):
            record_path = directory / TRANSACTION_RECORD
            if not record_path.is_file():
                continue
            try:
                record = json.loads(
                    record_path.read_text(encoding="utf-8")
                )
            except (OSError, json.JSONDecodeError):
                transactions.append(
                    {
                        "transaction_id": directory.name,
                        "status": "unreadable",
                    }
                )
                continue

            transactions.append(
                {
                    "transaction_id": record.get(
                        "transaction_id",
                        directory.name,
                    ),
                    "kind": record.get("kind"),
                    "status": record.get("status", "unknown"),
                    "package": record.get("package"),
                    "package_id": record.get("package_id"),
                    "name": record.get("name"),
                    "version": record.get("version"),
                    "created_utc": record.get("created_utc"),
                    "committed_utc": record.get("committed_utc"),
                    "rolled_back_utc": record.get("rolled_back_utc"),
                    "file_count": len(record.get("files", [])),
                }
            )
            if len(transactions) >= limit:
                break

        return {
            "count": len(transactions),
            "transactions": transactions,
        }

    def get_transaction(self, transaction_id: str) -> dict[str, Any]:
        return self._read_transaction(transaction_id)

    def list_installed_packages(self) -> dict[str, Any]:
        # Latest still-committed transaction per package_id is considered active.
        active: dict[str, dict[str, Any]] = {}

        for item in self.list_transactions(limit=100)["transactions"]:
            package_id = item.get("package_id")
            if not package_id or package_id in active:
                continue
            if item.get("kind") != "package_install":
                continue
            if item.get("status") == "committed":
                active[package_id] = item

        packages = sorted(
            active.values(),
            key=lambda item: str(item.get("name", "")).lower(),
        )
        return {
            "count": len(packages),
            "packages": packages,
        }

    def get_status(self, version: str) -> dict[str, Any]:
        transactions = self.list_transactions(limit=100)["transactions"]
        interrupted = [
            item
            for item in transactions
            if item.get("status") == "interrupted"
        ]
        latest = transactions[0] if transactions else None
        pending_path = self.state / PENDING_PLATFORM_UPDATE
        pending = None
        if pending_path.is_file():
            try:
                pending = json.loads(
                    pending_path.read_text(encoding="utf-8")
                )
            except json.JSONDecodeError:
                pending = {"status": "unreadable"}

        return {
            "version": version,
            "inbox_package_count": len(list(self.inbox.glob("*.zip"))),
            "transaction_count": len(transactions),
            "interrupted_transaction_count": len(interrupted),
            "recovery_required": bool(interrupted),
            "latest_transaction": latest,
            "pending_platform_update": pending,
            "paths": {
                "inbox": str(self.inbox),
                "staging": str(self.staging),
                "backups": str(self.backups),
                "platform_updates": str(self.platform_updates),
            },
        }

    # ------------------------------------------------------------------
    # Trusted-hash platform updater
    # ------------------------------------------------------------------

    def validate_platform_update(
        self,
        package_name: str,
        expected_sha256: str,
        current_version: str,
    ) -> dict[str, Any]:
        if not self._valid_sha256(expected_sha256):
            raise DeploymentError(
                "expected_sha256 must be a 64-character SHA-256 digest."
            )

        package = self._archive_path(
            self.platform_updates,
            package_name,
        )
        actual_archive_hash = self._sha256_file(package)
        if actual_archive_hash.lower() != expected_sha256.lower():
            raise DeploymentError(
                "Platform-update archive SHA-256 does not match the "
                "explicitly trusted expected_sha256 value."
            )

        with self._open_archive(package) as archive:
            self._validate_zip_metadata(archive)
            manifest = self._read_manifest(
                archive,
                FORMAT_PLATFORM_UPDATE,
            )

            if manifest.get("type") != "platform_update":
                raise DeploymentError(
                    "Format-2 package must declare type platform_update."
                )
            if manifest.get("domain") != PLATFORM_DOMAIN:
                raise DeploymentError(
                    "Platform update domain does not match JNS."
                )

            from_version = manifest.get("from_version")
            if isinstance(from_version, str):
                allowed_from = [from_version]
            elif isinstance(from_version, list) and all(
                isinstance(item, str) for item in from_version
            ):
                allowed_from = from_version
            else:
                raise DeploymentError(
                    "Platform update requires from_version string or list."
                )

            if "*" not in allowed_from and current_version not in allowed_from:
                raise DeploymentError(
                    f"Platform update does not permit upgrade from "
                    f"{current_version}."
                )

            to_version = manifest.get("to_version")
            if not isinstance(to_version, str) or not to_version.strip():
                raise DeploymentError(
                    "Platform update requires to_version."
                )

            validated: list[ValidatedFile] = []
            declared_members: set[str] = set()
            declared_targets: set[str] = set()
            target_data: dict[str, bytes] = {}

            for entry in manifest["files"]:
                if not isinstance(entry, dict):
                    raise DeploymentError(
                        "Each platform-update file entry must be an object."
                    )

                member = self._safe_posix_path(entry.get("source", ""))
                target = self._safe_posix_path(entry.get("target", ""))
                expected = str(entry.get("sha256", "")).lower()

                if not target.startswith(PLATFORM_TARGET_ROOT):
                    raise DeploymentError(
                        f"Platform update target is outside "
                        f"{PLATFORM_TARGET_ROOT}: {target}"
                    )
                if not self._valid_sha256(expected):
                    raise DeploymentError(
                        f"Invalid SHA-256 in platform manifest for {member}."
                    )
                if member in declared_members:
                    raise DeploymentError(
                        f"Platform manifest duplicates member: {member}"
                    )
                if target in declared_targets:
                    raise DeploymentError(
                        f"Platform manifest duplicates target: {target}"
                    )

                declared_members.add(member)
                declared_targets.add(target)

                try:
                    info = archive.getinfo(member)
                except KeyError as exc:
                    raise DeploymentError(
                        f"Platform manifest member missing: {member}"
                    ) from exc
                if info.is_dir():
                    raise DeploymentError(
                        f"Platform member must be a file: {member}"
                    )

                data = archive.read(member)
                actual = hashlib.sha256(data).hexdigest()
                if actual != expected:
                    raise DeploymentError(
                        f"Platform file SHA-256 mismatch for {member}"
                    )

                # Compile Python before touching the live integration.
                if target.endswith(".py"):
                    try:
                        compile(
                            data.decode("utf-8"),
                            target,
                            "exec",
                        )
                    except (UnicodeDecodeError, SyntaxError) as exc:
                        raise DeploymentError(
                            f"Platform Python validation failed for {target}: {exc}"
                        ) from exc

                target_data[target] = data
                validated.append(
                    ValidatedFile(
                        source_member=member,
                        target_rel=target,
                        sha256=actual,
                        size=len(data),
                    )
                )

            missing_required = sorted(
                PLATFORM_REQUIRED_TARGETS - declared_targets
            )
            if missing_required:
                raise DeploymentError(
                    "Platform update is missing required integration files: "
                    + ", ".join(missing_required)
                )

            embedded_manifest_target = (
                "custom_components/jns_deployment/manifest.json"
            )
            try:
                embedded_manifest = json.loads(
                    target_data[embedded_manifest_target].decode("utf-8")
                )
            except (KeyError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise DeploymentError(
                    "Platform update contains an invalid integration manifest."
                ) from exc

            if embedded_manifest.get("domain") != PLATFORM_DOMAIN:
                raise DeploymentError(
                    "Embedded integration manifest domain is incorrect."
                )
            if embedded_manifest.get("version") != to_version:
                raise DeploymentError(
                    "Embedded integration version does not match to_version."
                )

            allowed_archive_members = declared_members | {PACKAGE_MANIFEST}
            undeclared = []
            for info in archive.infolist():
                if info.is_dir():
                    continue
                normalized = self._safe_posix_path(info.filename)
                if normalized not in allowed_archive_members:
                    undeclared.append(normalized)
            if undeclared:
                raise DeploymentError(
                    "Platform package contains undeclared files: "
                    + ", ".join(sorted(undeclared))
                )

        return {
            "ok": True,
            "kind": "platform_update",
            "package": package_name,
            "package_sha256": actual_archive_hash,
            "name": manifest["name"],
            "version": manifest["version"],
            "from_version": allowed_from,
            "to_version": to_version,
            "file_count": len(validated),
            "files": [asdict(item) for item in validated],
            "trust_model": "explicit_expected_archive_sha256",
        }

    def install_platform_update(
        self,
        package_name: str,
        expected_sha256: str,
        current_version: str,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        with self._exclusive_operation():
            validation = self.validate_platform_update(
                package_name,
                expected_sha256,
                current_version,
            )
            if dry_run:
                return {
                    **validation,
                    "dry_run": True,
                    "installed": False,
                    "requires_restart": True,
                }

            package = self._archive_path(
                self.platform_updates,
                package_name,
            )
            transaction_id = (
                time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
                + "-platform-"
                + uuid.uuid4().hex[:8]
            )
            tx_root = (self.backups / transaction_id).resolve()
            tx_root.mkdir(parents=True, exist_ok=False)
            tx_path = tx_root / TRANSACTION_RECORD

            live_root = (
                self.config_root
                / "custom_components"
                / "jns_deployment"
            ).resolve()
            live_parent = live_root.parent
            stage_root = (
                live_parent / f".jns_deployment_stage_{transaction_id}"
            ).resolve()
            hold_root = (
                live_parent / f".jns_deployment_old_{transaction_id}"
            ).resolve()
            backup_tree = tx_root / "platform_backup" / "jns_deployment"

            for path in (stage_root, hold_root):
                if path.exists():
                    shutil.rmtree(path)

            transaction = {
                "transaction_id": transaction_id,
                "kind": "platform_update",
                "package": package_name,
                "package_sha256": validation["package_sha256"],
                "name": validation["name"],
                "from_version": current_version,
                "to_version": validation["to_version"],
                "created_utc": time.strftime(
                    "%Y-%m-%dT%H:%M:%SZ",
                    time.gmtime(),
                ),
                "status": "staging",
            }
            self._write_json_atomic(tx_path, transaction)

            try:
                stage_root.mkdir(parents=True, exist_ok=False)

                with self._open_archive(package) as archive:
                    manifest = self._read_manifest(
                        archive,
                        FORMAT_PLATFORM_UPDATE,
                    )

                    for entry in manifest["files"]:
                        target = self._safe_posix_path(entry["target"])
                        relative = PurePosixPath(target).relative_to(
                            PurePosixPath(PLATFORM_TARGET_ROOT.rstrip("/"))
                        )
                        destination = (stage_root / str(relative)).resolve()
                        if stage_root not in destination.parents:
                            raise DeploymentError(
                                "Platform staging path escaped staging root."
                            )
                        destination.parent.mkdir(
                            parents=True,
                            exist_ok=True,
                        )
                        data = archive.read(entry["source"])
                        destination.write_bytes(data)
                        if self._sha256_file(destination) != entry["sha256"].lower():
                            raise DeploymentError(
                                f"Platform staged hash mismatch: {target}"
                            )

                # Backup the complete old integration tree, including files
                # that are intentionally absent from the new release.
                if live_root.is_dir():
                    backup_tree.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copytree(live_root, backup_tree)
                else:
                    raise DeploymentError(
                        "Current JNS integration directory is missing."
                    )

                transaction["status"] = "committing"
                transaction["backup_tree"] = str(
                    backup_tree.relative_to(tx_root)
                )
                self._write_json_atomic(tx_path, transaction)

                # Same-parent directory renames keep the replacement window
                # as small as possible and avoid stale files.
                os.replace(live_root, hold_root)
                try:
                    os.replace(stage_root, live_root)
                except Exception:
                    os.replace(hold_root, live_root)
                    raise

                # Verify every installed target after directory replacement.
                for item in validation["files"]:
                    live = (
                        self.config_root / item["target_rel"]
                    ).resolve()
                    if not live.is_file():
                        raise DeploymentError(
                            f"Platform target missing after update: "
                            f"{item['target_rel']}"
                        )
                    if self._sha256_file(live) != item["sha256"]:
                        raise DeploymentError(
                            f"Platform post-commit hash mismatch: "
                            f"{item['target_rel']}"
                        )

                shutil.rmtree(hold_root, ignore_errors=True)

                transaction["status"] = "pending_restart"
                transaction["committed_utc"] = time.strftime(
                    "%Y-%m-%dT%H:%M:%SZ",
                    time.gmtime(),
                )
                self._write_json_atomic(tx_path, transaction)

                pending = {
                    "transaction_id": transaction_id,
                    "from_version": current_version,
                    "to_version": validation["to_version"],
                    "status": "pending_restart",
                    "created_utc": transaction["created_utc"],
                }
                self._write_json_atomic(
                    self.state / PENDING_PLATFORM_UPDATE,
                    pending,
                )

                return {
                    "ok": True,
                    "kind": "platform_update",
                    "installed": True,
                    "dry_run": False,
                    "transaction_id": transaction_id,
                    "from_version": current_version,
                    "to_version": validation["to_version"],
                    "requires_restart": True,
                }

            except Exception:
                # Restore the original tree if it had already been moved.
                try:
                    if hold_root.is_dir():
                        if live_root.exists():
                            shutil.rmtree(live_root)
                        os.replace(hold_root, live_root)
                    elif backup_tree.is_dir() and not live_root.exists():
                        shutil.copytree(backup_tree, live_root)
                finally:
                    shutil.rmtree(stage_root, ignore_errors=True)
                    transaction["status"] = "rolled_back_after_failure"
                    self._write_json_atomic(tx_path, transaction)
                raise
            finally:
                shutil.rmtree(stage_root, ignore_errors=True)

    def confirm_pending_platform_update(
        self,
        current_version: str,
    ) -> dict[str, Any] | None:
        pending_path = self.state / PENDING_PLATFORM_UPDATE
        if not pending_path.is_file():
            return None

        try:
            pending = json.loads(
                pending_path.read_text(encoding="utf-8")
            )
        except json.JSONDecodeError:
            return None

        transaction_id = pending.get("transaction_id")
        to_version = pending.get("to_version")
        if not isinstance(transaction_id, str):
            return None

        if current_version == to_version:
            try:
                record = self._read_transaction(transaction_id)
            except DeploymentError:
                return None

            record["status"] = "confirmed"
            record["confirmed_utc"] = time.strftime(
                "%Y-%m-%dT%H:%M:%SZ",
                time.gmtime(),
            )
            self._write_json_atomic(
                self._transaction_path(transaction_id),
                record,
            )
            pending["status"] = "confirmed"
            pending["confirmed_utc"] = record["confirmed_utc"]
            self._write_json_atomic(pending_path, pending)
            return pending

        pending["status"] = "version_mismatch"
        pending["running_version"] = current_version
        self._write_json_atomic(pending_path, pending)
        return pending

    def rollback_platform_update(
        self,
        transaction_id: str,
    ) -> dict[str, Any]:
        with self._exclusive_operation():
            record = self._read_transaction(transaction_id)
            if record.get("kind") != "platform_update":
                raise DeploymentError(
                    "Transaction is not a platform update."
                )

            tx_root = self._transaction_path(transaction_id).parent
            backup_tree = (
                tx_root / "platform_backup" / "jns_deployment"
            ).resolve()
            if not backup_tree.is_dir():
                raise DeploymentError(
                    "Platform update backup tree is missing."
                )

            live_root = (
                self.config_root
                / "custom_components"
                / "jns_deployment"
            ).resolve()
            live_parent = live_root.parent
            hold_root = (
                live_parent / f".jns_platform_rollback_{transaction_id}"
            ).resolve()
            if hold_root.exists():
                shutil.rmtree(hold_root)

            if live_root.exists():
                os.replace(live_root, hold_root)
            try:
                shutil.copytree(backup_tree, live_root)
            except Exception:
                if hold_root.exists() and not live_root.exists():
                    os.replace(hold_root, live_root)
                raise

            shutil.rmtree(hold_root, ignore_errors=True)
            record["status"] = "platform_rolled_back"
            record["platform_rolled_back_utc"] = time.strftime(
                "%Y-%m-%dT%H:%M:%SZ",
                time.gmtime(),
            )
            self._write_json_atomic(
                self._transaction_path(transaction_id),
                record,
            )

            pending_path = self.state / PENDING_PLATFORM_UPDATE
            if pending_path.is_file():
                pending_path.unlink()

            return {
                "ok": True,
                "transaction_id": transaction_id,
                "requires_restart": True,
                "restored_version": record.get("from_version"),
            }
