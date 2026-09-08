from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterator
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

try:
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None

from .audit import AuditError, AuditLog
from .const import (
    CONFIG_ALLOWED_EXTENSIONS,
    CONFIG_ALLOWED_ROOTS,
    MAX_COMPRESSION_RATIO,
    MAX_MEMBER_BYTES,
    MAX_MEMBER_COUNT,
    MAX_PACKAGE_BYTES,
    MAX_TOTAL_UNCOMPRESSED_BYTES,
    MIN_FREE_SPACE_RESERVE,
    OPERATION_LOCK_FILE,
    PACKAGE_MANIFEST,
    PACKAGE_SIGNATURE,
    PENDING_PLATFORM_UPDATE,
    PLATFORM_DOMAIN,
    PLATFORM_REQUIRED_TARGETS,
    PLATFORM_TARGET_ROOT,
    SIGNED_PACKAGE_FORMAT,
    TRANSACTION_RECORD,
)
from .security import SecurityError, TrustStore


class DeploymentError(Exception):
    """Expected JNS validation, policy, transaction, or rollback failure."""


@dataclass(frozen=True)
class ValidatedFile:
    source_member: str
    target_rel: str
    sha256: str
    size: int


class DeploymentManager:
    """Production JNS signed-package deployment engine."""

    def __init__(
        self,
        config_root: Path,
        inbox_rel: str,
        staging_rel: str,
        backups_rel: str,
        state_rel: str,
        platform_updates_rel: str,
        trust_rel: str,
        audit_rel: str,
        quarantine_rel: str,
        recovery_rel: str,
    ) -> None:
        self.config_root = config_root.resolve()
        self.inbox = (self.config_root / inbox_rel).resolve()
        self.staging = (self.config_root / staging_rel).resolve()
        self.backups = (self.config_root / backups_rel).resolve()
        self.state = (self.config_root / state_rel).resolve()
        self.platform_updates = (self.config_root / platform_updates_rel).resolve()
        self.trust_dir = (self.config_root / trust_rel).resolve()
        self.audit_dir = (self.config_root / audit_rel).resolve()
        self.quarantine = (self.config_root / quarantine_rel).resolve()
        self.recovery_dir = (self.config_root / recovery_rel).resolve()

        for path in (
            self.inbox,
            self.staging,
            self.backups,
            self.state,
            self.platform_updates,
            self.trust_dir,
            self.audit_dir,
            self.quarantine,
            self.recovery_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)

        self.trust = TrustStore(self.trust_dir)
        self.audit = AuditLog(self.audit_dir)
        self._thread_lock = threading.Lock()
        self.lock_path = self.state / OPERATION_LOCK_FILE
        self._mark_interrupted_transactions()

    # ----- durable filesystem helpers -----

    @staticmethod
    def _sha256_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    @staticmethod
    def _fsync_dir(path: Path) -> None:
        try:
            fd = os.open(path, os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    @classmethod
    def _write_bytes_atomic(cls, path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=".jns-", dir=str(path.parent))
        temp_path = Path(temp_name)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, path)
            cls._fsync_dir(path.parent)
        finally:
            temp_path.unlink(missing_ok=True)

    @classmethod
    def _write_json_atomic(cls, path: Path, data: dict[str, Any]) -> None:
        cls._write_bytes_atomic(
            path,
            (json.dumps(data, indent=2, sort_keys=True) + "\n").encode("utf-8"),
        )

    @classmethod
    def _copy_file_durable(cls, source: Path, target: Path) -> None:
        cls._write_bytes_atomic(target, source.read_bytes())
        try:
            shutil.copystat(source, target)
        except OSError:
            pass

    @staticmethod
    def _safe_posix_path(value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise DeploymentError("Empty package path is not allowed.")
        if "\x00" in value:
            raise DeploymentError("NUL bytes are not allowed in package paths.")
        if "\\" in value:
            raise DeploymentError(f"Backslashes are not allowed in package paths: {value!r}")
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts or "." in path.parts:
            raise DeploymentError(f"Unsafe package path: {value!r}")
        normalized = str(path)
        if not normalized or normalized.startswith("/"):
            raise DeploymentError(f"Unsafe package path: {value!r}")
        return normalized

    @staticmethod
    def _package_id(manifest: dict[str, Any]) -> str:
        package_id = str(manifest.get("package_id", "")).strip().lower()
        if not package_id:
            package_id = re.sub(
                r"[^a-z0-9]+", "_", str(manifest.get("name", "")).lower()
            ).strip("_")
        if not package_id or len(package_id) > 80:
            raise DeploymentError("Package id is empty or too long.")
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", package_id):
            raise DeploymentError(
                "Package id may contain lowercase letters, digits, '_' and '-'."
            )
        return package_id

    # ----- locking/audit -----

    @contextmanager
    def _exclusive_operation(self) -> Iterator[None]:
        if not self._thread_lock.acquire(blocking=False):
            raise DeploymentError("Another JNS operation is already in progress.")
        lock_handle = None
        try:
            self.lock_path.touch(exist_ok=True)
            lock_handle = self.lock_path.open("r+")
            if fcntl is not None:
                try:
                    fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError as exc:
                    raise DeploymentError(
                        "Another JNS process holds the deployment lock."
                    ) from exc
            yield
        finally:
            if lock_handle is not None:
                if fcntl is not None:
                    try:
                        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
                    except OSError:
                        pass
                lock_handle.close()
            self._thread_lock.release()

    def _require_audit_integrity(self) -> None:
        try:
            self.audit.verify()
        except AuditError as exc:
            raise DeploymentError(
                "JNS audit-chain integrity verification failed. New deployments are "
                f"blocked until the audit log is reviewed: {exc}"
            ) from exc

    def verify_audit_log(self) -> dict[str, Any]:
        try:
            return self.audit.verify()
        except AuditError as exc:
            raise DeploymentError(str(exc)) from exc

    def _audit(self, event: str, details: dict[str, Any]) -> None:
        try:
            self.audit.append(event, details)
        except AuditError as exc:
            raise DeploymentError(f"Unable to append verified JNS audit event: {exc}") from exc

    # ----- status/trust -----

    def list_trusted_publishers(self) -> dict[str, Any]:
        try:
            return self.trust.list_publishers()
        except SecurityError as exc:
            raise DeploymentError(str(exc)) from exc

    def get_status(self, version: str) -> dict[str, Any]:
        try:
            audit_state = self.audit.verify()
        except AuditError as exc:
            audit_state = {"ok": False, "error": str(exc), "path": str(self.audit.path)}
        try:
            trust_state = self.trust.list_publishers()
        except SecurityError as exc:
            trust_state = {
                "configured": True,
                "count": 0,
                "error": str(exc),
                "path": str(self.trust.path),
            }
        transactions = self.list_transactions(100)["transactions"]
        interrupted = [item for item in transactions if item.get("status") == "interrupted"]
        pending = None
        pending_path = self.state / PENDING_PLATFORM_UPDATE
        if pending_path.is_file():
            try:
                pending = json.loads(pending_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pending = {"status": "unreadable"}
        return {
            "version": version,
            "production_signed_packages_required": True,
            "trust": trust_state,
            "audit": audit_state,
            "inbox_package_count": len(list(self.inbox.glob("*.zip"))),
            "transaction_count": len(transactions),
            "interrupted_transaction_count": len(interrupted),
            "recovery_required": bool(interrupted),
            "latest_transaction": transactions[0] if transactions else None,
            "pending_platform_update": pending,
            "paths": {
                "inbox": str(self.inbox),
                "staging": str(self.staging),
                "backups": str(self.backups),
                "platform_updates": str(self.platform_updates),
                "trust": str(self.trust_dir),
                "audit": str(self.audit_dir),
                "quarantine": str(self.quarantine),
                "recovery": str(self.recovery_dir),
            },
        }

    # ----- transaction helpers -----

    def _transaction_path(self, transaction_id: str) -> Path:
        if Path(transaction_id).name != transaction_id:
            raise DeploymentError("Invalid transaction id.")
        root = (self.backups / transaction_id).resolve()
        if root.parent != self.backups:
            raise DeploymentError("Transaction path escaped backup root.")
        return root / TRANSACTION_RECORD

    def _read_transaction(self, transaction_id: str) -> dict[str, Any]:
        path = self._transaction_path(transaction_id)
        if not path.is_file():
            raise DeploymentError("Transaction record not found.")
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise DeploymentError("Transaction record is not valid JSON.") from exc

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
                    "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
                )
                self._write_json_atomic(record_path, record)

    # ----- archive/signature validation -----

    def _archive_path(self, root: Path, package_name: str) -> Path:
        if Path(package_name).name != package_name:
            raise DeploymentError("Package must be a filename only, not a filesystem path.")
        if not package_name.lower().endswith(".zip"):
            raise DeploymentError("Only ZIP packages are accepted.")
        package = (root / package_name).resolve()
        if package.parent != root:
            raise DeploymentError("Package path escaped its JNS inbox.")
        if not package.is_file():
            raise DeploymentError(f"Package not found in {root}: {package_name}")
        if package.stat().st_size > MAX_PACKAGE_BYTES:
            raise DeploymentError("Package exceeds maximum permitted compressed size.")
        return package

    @staticmethod
    def _open_archive(path: Path) -> zipfile.ZipFile:
        try:
            return zipfile.ZipFile(path, "r")
        except zipfile.BadZipFile as exc:
            raise DeploymentError("Package is not a valid ZIP archive.") from exc

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
                raise DeploymentError(f"Encrypted ZIP members are not permitted: {name}")
            mode = (info.external_attr >> 16) & 0xFFFF
            if mode:
                file_type = stat.S_IFMT(mode)
                if file_type not in (0, stat.S_IFREG, stat.S_IFDIR):
                    raise DeploymentError(f"Special files are forbidden in packages: {name}")
            if info.file_size > MAX_MEMBER_BYTES:
                raise DeploymentError(f"Archive member exceeds maximum size: {name}")
            total_uncompressed += info.file_size
            if total_uncompressed > MAX_TOTAL_UNCOMPRESSED_BYTES:
                raise DeploymentError("Package exceeds maximum total uncompressed size.")
            if info.file_size and info.compress_size:
                ratio = info.file_size / info.compress_size
                if ratio > MAX_COMPRESSION_RATIO:
                    raise DeploymentError(
                        f"Archive member compression ratio is too high: {name}"
                    )

    def _read_signed_metadata(
        self,
        archive: zipfile.ZipFile,
        expected_type: str,
        required_scope: str,
    ) -> tuple[dict[str, Any], str]:
        try:
            manifest_raw = archive.read(PACKAGE_MANIFEST)
            signature_raw = archive.read(PACKAGE_SIGNATURE)
        except KeyError as exc:
            raise DeploymentError(
                "Production package requires jns_package.json and jns_signature.json."
            ) from exc
        try:
            manifest = json.loads(manifest_raw.decode("utf-8"))
            signature = json.loads(signature_raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise DeploymentError("Package manifest/signature metadata is invalid JSON.") from exc
        if manifest.get("format") != SIGNED_PACKAGE_FORMAT:
            raise DeploymentError(
                "Unsigned/legacy packages are disabled in JNS v5. Sign as format 3."
            )
        if manifest.get("type") != expected_type:
            raise DeploymentError(f"Expected package type {expected_type!r}.")
        if not isinstance(manifest.get("name"), str) or not manifest["name"].strip():
            raise DeploymentError("Manifest requires a package name.")
        if not isinstance(manifest.get("version"), str) or not manifest["version"].strip():
            raise DeploymentError("Manifest requires a package version.")
        if not isinstance(manifest.get("files"), list) or not manifest["files"]:
            raise DeploymentError("Manifest requires a non-empty files list.")
        try:
            publisher = self.trust.verify(
                manifest_raw, manifest, signature, required_scope
            )
        except SecurityError as exc:
            raise DeploymentError(str(exc)) from exc
        return manifest, publisher.fingerprint_sha256

    @staticmethod
    def _valid_sha256(value: str) -> bool:
        return (
            isinstance(value, str)
            and len(value) == 64
            and all(char in "0123456789abcdefABCDEF" for char in value)
        )

    def _validate_declared_files(
        self,
        archive: zipfile.ZipFile,
        manifest: dict[str, Any],
        target_validator: Callable[[str], None],
    ) -> list[ValidatedFile]:
        validated: list[ValidatedFile] = []
        declared_members: set[str] = set()
        declared_targets: set[str] = set()
        for entry in manifest["files"]:
            if not isinstance(entry, dict):
                raise DeploymentError("Each manifest files entry must be an object.")
            member = self._safe_posix_path(entry.get("source", ""))
            target = self._safe_posix_path(entry.get("target", ""))
            expected = str(entry.get("sha256", "")).lower()
            if member in {PACKAGE_MANIFEST, PACKAGE_SIGNATURE}:
                raise DeploymentError("Metadata files cannot be deployment payloads.")
            target_validator(target)
            if not self._valid_sha256(expected):
                raise DeploymentError(f"Invalid SHA-256 in manifest for {member}.")
            if member in declared_members:
                raise DeploymentError(f"Manifest duplicates source member: {member}")
            if target in declared_targets:
                raise DeploymentError(f"Manifest duplicates deployment target: {target}")
            declared_members.add(member)
            declared_targets.add(target)
            try:
                info = archive.getinfo(member)
            except KeyError as exc:
                raise DeploymentError(f"Manifest member missing from ZIP: {member}") from exc
            if info.is_dir():
                raise DeploymentError(f"Manifest member must be a file: {member}")
            data = archive.read(member)
            actual = hashlib.sha256(data).hexdigest()
            if actual != expected:
                raise DeploymentError(
                    f"SHA-256 mismatch for {member}: expected {expected}, got {actual}"
                )
            validated.append(
                ValidatedFile(member, target, actual, len(data))
            )
        allowed = declared_members | {PACKAGE_MANIFEST, PACKAGE_SIGNATURE}
        undeclared = []
        for info in archive.infolist():
            if info.is_dir():
                continue
            normalized = self._safe_posix_path(info.filename)
            if normalized not in allowed:
                undeclared.append(normalized)
        if undeclared:
            raise DeploymentError(
                "Package contains undeclared files: " + ", ".join(sorted(undeclared))
            )
        return validated

    # ----- signed configuration packages -----

    @staticmethod
    def _validate_config_target(target: str) -> None:
        for prefix, extensions in CONFIG_ALLOWED_EXTENSIONS.items():
            if target.startswith(prefix):
                suffix = PurePosixPath(target).suffix.lower()
                if suffix not in extensions:
                    raise DeploymentError(
                        f"Target file type is not permitted under {prefix}: {target}"
                    )
                return
        raise DeploymentError(
            f"Target is outside production config roots: {target}. "
            f"Allowed roots: {', '.join(CONFIG_ALLOWED_ROOTS)}"
        )

    def validate_package(self, package_name: str) -> dict[str, Any]:
        package = self._archive_path(self.inbox, package_name)
        package_sha256 = self._sha256_file(package)
        with self._open_archive(package) as archive:
            self._validate_zip_metadata(archive)
            manifest, fingerprint = self._read_signed_metadata(
                archive, "config_package", "config"
            )
            package_id = self._package_id(manifest)
            validated = self._validate_declared_files(
                archive, manifest, self._validate_config_target
            )
        return {
            "ok": True,
            "kind": "config_package",
            "signed": True,
            "package": package_name,
            "package_id": package_id,
            "package_sha256": package_sha256,
            "publisher_id": manifest["publisher_id"],
            "publisher_fingerprint_sha256": fingerprint,
            "name": manifest["name"],
            "version": manifest["version"],
            "file_count": len(validated),
            "files": [asdict(item) for item in validated],
        }

    def plan_package(self, package_name: str) -> dict[str, Any]:
        validation = self.validate_package(package_name)
        changes = []
        for item in validation["files"]:
            target = item["target_rel"]
            live = (self.config_root / target).resolve()
            if self.config_root not in live.parents:
                raise DeploymentError(f"Target escaped Home Assistant config root: {target}")
            if live.is_symlink():
                action, current_hash = "blocked_symlink", None
            elif live.is_dir():
                action, current_hash = "blocked_directory", None
            elif live.is_file():
                current_hash = self._sha256_file(live)
                action = "unchanged" if current_hash == item["sha256"] else "replace"
            else:
                action, current_hash = "create", None
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
                1 for item in changes if item["action"] in {"create", "replace"}
            ),
            "blocked_count": sum(
                1 for item in changes if item["action"].startswith("blocked_")
            ),
        }

    def _preflight_disk_space(self, plan: dict[str, Any]) -> dict[str, int]:
        required = 0
        for item in plan["files"]:
            required += int(item["size"])
            live = (self.config_root / item["target_rel"]).resolve()
            if live.is_file():
                required += live.stat().st_size
        required += MIN_FREE_SPACE_RESERVE
        free = shutil.disk_usage(self.config_root).free
        if free < required:
            raise DeploymentError(
                f"Insufficient free disk space. Need {required} bytes including reserve; "
                f"available {free}."
            )
        return {"required_with_reserve": required, "available": free}

    def install_package(self, package_name: str, dry_run: bool = False) -> dict[str, Any]:
        with self._exclusive_operation():
            self._require_audit_integrity()
            plan = self.plan_package(package_name)
            if plan["blocked_count"]:
                raise DeploymentError("Deployment plan contains blocked target paths.")
            disk = self._preflight_disk_space(plan)
            if dry_run:
                return {**plan, "disk_space": disk, "dry_run": True, "installed": False}

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
            transaction = {
                "transaction_id": transaction_id,
                "kind": "package_install",
                "package": package_name,
                "package_id": plan["package_id"],
                "package_sha256": plan["package_sha256"],
                "publisher_id": plan["publisher_id"],
                "publisher_fingerprint_sha256": plan["publisher_fingerprint_sha256"],
                "name": plan["name"],
                "version": plan["version"],
                "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "files": [],
                "status": "staging",
            }
            self._write_json_atomic(transaction_path, transaction)
            self._audit(
                "package_install_started",
                {
                    "transaction_id": transaction_id,
                    "package_id": plan["package_id"],
                    "package_sha256": plan["package_sha256"],
                    "publisher_id": plan["publisher_id"],
                    "version": plan["version"],
                },
            )
            try:
                with self._open_archive(package) as archive:
                    self._validate_zip_metadata(archive)
                    manifest, _ = self._read_signed_metadata(
                        archive, "config_package", "config"
                    )
                    self._validate_declared_files(
                        archive, manifest, self._validate_config_target
                    )
                    for entry in manifest["files"]:
                        target = self._safe_posix_path(entry["target"])
                        staged = (stage_root / target).resolve()
                        if stage_root not in staged.parents:
                            raise DeploymentError(
                                f"Staged path escaped transaction root: {target}"
                            )
                        self._write_bytes_atomic(staged, archive.read(entry["source"]))
                        if self._sha256_file(staged) != entry["sha256"].lower():
                            raise DeploymentError(f"Staged hash mismatch for {target}")

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
                        if live.is_symlink():
                            raise DeploymentError(
                                f"Refusing to overwrite symbolic link: {target}"
                            )
                        if live.is_dir():
                            raise DeploymentError(
                                f"Refusing to overwrite directory with file: {target}"
                            )
                        existed = live.is_file()
                        current_hash = self._sha256_file(live) if existed else None
                        if existed and current_hash == expected_hash:
                            transaction["files"].append(
                                {
                                    "target": target,
                                    "action": "unchanged",
                                    "previously_existed": True,
                                    "backup_sha256": None,
                                    "installed_sha256": expected_hash,
                                }
                            )
                            self._write_json_atomic(transaction_path, transaction)
                            continue

                        backup_sha256 = None
                        if existed:
                            self._copy_file_durable(live, backup)
                            backup_sha256 = self._sha256_file(backup)
                        item = {
                            "target": target,
                            "action": "replace" if existed else "create",
                            "previously_existed": existed,
                            "backup_sha256": backup_sha256,
                            "installed_sha256": None,
                        }
                        transaction["files"].append(item)
                        self._write_json_atomic(transaction_path, transaction)
                        self._copy_file_durable(staged, live)
                        installed_hash = self._sha256_file(live)
                        if installed_hash != expected_hash:
                            raise DeploymentError(
                                f"Post-commit hash mismatch for {target}"
                            )
                        item["installed_sha256"] = installed_hash
                        self._write_json_atomic(transaction_path, transaction)

                transaction["status"] = "committed"
                transaction["committed_utc"] = time.strftime(
                    "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
                )
                self._write_json_atomic(transaction_path, transaction)
                changed_count = sum(
                    1 for item in transaction["files"] if item["action"] != "unchanged"
                )
                self._audit(
                    "package_install_committed",
                    {
                        "transaction_id": transaction_id,
                        "package_id": plan["package_id"],
                        "changed_count": changed_count,
                    },
                )
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
                    "publisher_id": plan["publisher_id"],
                    "file_count": len(transaction["files"]),
                    "changed_count": changed_count,
                }
            except Exception as exc:
                self._rollback_partial_install(transaction, backup_root)
                self._write_json_atomic(transaction_path, transaction)
                self._audit(
                    "package_install_failed",
                    {
                        "transaction_id": transaction_id,
                        "package_id": plan["package_id"],
                        "error": str(exc)[:500],
                        "final_status": transaction["status"],
                    },
                )
                raise
            finally:
                shutil.rmtree(stage_root, ignore_errors=True)

    def _rollback_partial_install(
        self, transaction: dict[str, Any], backup_root: Path
    ) -> None:
        errors = []
        for item in reversed(transaction.get("files", [])):
            if item.get("action") == "unchanged":
                continue
            target = item["target"]
            live = (self.config_root / target).resolve()
            backup = (backup_root / target).resolve()
            try:
                if item["previously_existed"]:
                    if not backup.is_file():
                        raise OSError("required rollback backup missing")
                    self._copy_file_durable(backup, live)
                elif live.is_file():
                    live.unlink()
                    self._fsync_dir(live.parent)
            except OSError as exc:
                errors.append(f"{target}: {exc}")
        transaction["status"] = (
            "rollback_failed_after_install_failure" if errors else "rolled_back_after_failure"
        )
        if errors:
            transaction["rollback_errors"] = errors

    # ----- rollback / interrupted recovery -----

    def rollback_transaction(
        self, transaction_id: str, force: bool = False
    ) -> dict[str, Any]:
        with self._exclusive_operation():
            record = self._read_transaction(transaction_id)
            if record.get("kind") != "package_install":
                raise DeploymentError("This transaction is not a normal package installation.")
            if record.get("status") == "rolled_back":
                raise DeploymentError("Transaction is already rolled back.")
            if record.get("status") != "committed":
                raise DeploymentError(
                    f"Transaction cannot be rolled back from status {record.get('status')!r}."
                )
            tx_root = self._transaction_path(transaction_id).parent
            files = record.get("files", [])
            if not isinstance(files, list):
                raise DeploymentError("Transaction record is invalid.")
            for item in files:
                if item.get("action") == "unchanged":
                    continue
                target = self._safe_posix_path(item["target"])
                live = (self.config_root / target).resolve()
                if self.config_root not in live.parents:
                    raise DeploymentError(f"Rollback target escaped config root: {target}")
                installed_hash = item.get("installed_sha256")
                if live.is_file() and installed_hash and not force:
                    if self._sha256_file(live) != installed_hash:
                        raise DeploymentError(
                            f"Refusing rollback because {target} changed after deployment. "
                            "Use force only after review."
                        )
                if item.get("previously_existed"):
                    backup = (tx_root / target).resolve()
                    if not backup.is_file():
                        raise DeploymentError(f"Required rollback file is missing: {target}")
                    expected = item.get("backup_sha256")
                    if expected and self._sha256_file(backup) != expected:
                        raise DeploymentError(f"Rollback backup hash mismatch for {target}")
            restored = []
            for item in reversed(files):
                if item.get("action") == "unchanged":
                    continue
                target = self._safe_posix_path(item["target"])
                live = (self.config_root / target).resolve()
                backup = (tx_root / target).resolve()
                if item.get("previously_existed"):
                    self._copy_file_durable(backup, live)
                elif live.is_file():
                    live.unlink()
                    self._fsync_dir(live.parent)
                restored.append(target)
            record["status"] = "rolled_back"
            record["rolled_back_utc"] = time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
            )
            record["rollback_forced"] = bool(force)
            self._write_json_atomic(self._transaction_path(transaction_id), record)
            self._audit(
                "package_transaction_rolled_back",
                {
                    "transaction_id": transaction_id,
                    "forced": bool(force),
                    "restored_count": len(restored),
                },
            )
            return {
                "ok": True,
                "transaction_id": transaction_id,
                "restored_count": len(restored),
                "restored": restored,
                "forced": bool(force),
            }

    def recover_interrupted_transaction(self, transaction_id: str) -> dict[str, Any]:
        with self._exclusive_operation():
            record = self._read_transaction(transaction_id)
            if record.get("kind") != "package_install":
                raise DeploymentError("Only package installs use this recovery action.")
            if record.get("status") != "interrupted":
                raise DeploymentError("Transaction is not marked as interrupted.")
            tx_root = self._transaction_path(transaction_id).parent
            restored = []
            for item in reversed(record.get("files", [])):
                if item.get("action") == "unchanged":
                    continue
                target = self._safe_posix_path(item["target"])
                live = (self.config_root / target).resolve()
                backup = (tx_root / target).resolve()
                if item.get("previously_existed"):
                    if not backup.is_file():
                        raise DeploymentError(f"Interrupted transaction backup missing: {target}")
                    expected = item.get("backup_sha256")
                    if expected and self._sha256_file(backup) != expected:
                        raise DeploymentError(f"Interrupted backup hash mismatch: {target}")
                    self._copy_file_durable(backup, live)
                elif live.is_file():
                    live.unlink()
                    self._fsync_dir(live.parent)
                restored.append(target)
            record["status"] = "recovered"
            record["recovered_utc"] = time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
            )
            self._write_json_atomic(self._transaction_path(transaction_id), record)
            self._audit(
                "interrupted_transaction_recovered",
                {"transaction_id": transaction_id, "restored_count": len(restored)},
            )
            return {
                "ok": True,
                "transaction_id": transaction_id,
                "status": "recovered",
                "restored": restored,
            }

    # ----- inventory / quarantine -----

    def list_inbox_packages(self) -> dict[str, Any]:
        packages = []
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
                        "signed": True,
                        "publisher_id": validation["publisher_id"],
                        "package_id": validation["package_id"],
                        "name": validation["name"],
                        "version": validation["version"],
                        "file_count": validation["file_count"],
                    }
                )
            packages.append(item)
        return {"count": len(packages), "packages": packages}

    def quarantine_package(self, package_name: str, reason: str) -> dict[str, Any]:
        with self._exclusive_operation():
            source = self._archive_path(self.inbox, package_name)
            digest = self._sha256_file(source)
            stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
            target = self.quarantine / f"{stamp}_{digest[:12]}_{source.name}"
            os.replace(source, target)
            self._fsync_dir(self.inbox)
            self._fsync_dir(self.quarantine)
            metadata = {
                "original_name": source.name,
                "quarantined_name": target.name,
                "sha256": digest,
                "reason": reason[:500],
                "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            self._write_json_atomic(target.with_suffix(target.suffix + ".json"), metadata)
            self._audit("package_quarantined", metadata)
            return {"ok": True, **metadata}

    def list_transactions(self, limit: int = 50) -> dict[str, Any]:
        limit = max(1, min(int(limit), 100))
        transactions = []
        for directory in sorted(
            (path for path in self.backups.iterdir() if path.is_dir()),
            key=lambda path: path.name,
            reverse=True,
        ):
            record_path = directory / TRANSACTION_RECORD
            if not record_path.is_file():
                continue
            try:
                record = json.loads(record_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                transactions.append(
                    {"transaction_id": directory.name, "status": "unreadable"}
                )
                continue
            transactions.append(
                {
                    "transaction_id": record.get("transaction_id", directory.name),
                    "kind": record.get("kind"),
                    "status": record.get("status", "unknown"),
                    "package": record.get("package"),
                    "package_id": record.get("package_id"),
                    "publisher_id": record.get("publisher_id"),
                    "name": record.get("name"),
                    "version": record.get("version"),
                    "from_version": record.get("from_version"),
                    "to_version": record.get("to_version"),
                    "created_utc": record.get("created_utc"),
                    "committed_utc": record.get("committed_utc"),
                    "rolled_back_utc": record.get("rolled_back_utc"),
                    "file_count": len(record.get("files", [])),
                }
            )
            if len(transactions) >= limit:
                break
        return {"count": len(transactions), "transactions": transactions}

    def get_transaction(self, transaction_id: str) -> dict[str, Any]:
        return self._read_transaction(transaction_id)

    def list_installed_packages(self) -> dict[str, Any]:
        active: dict[str, dict[str, Any]] = {}
        for item in self.list_transactions(100)["transactions"]:
            package_id = item.get("package_id")
            if not package_id or package_id in active:
                continue
            if item.get("kind") == "package_install" and item.get("status") == "committed":
                active[package_id] = item
        packages = sorted(active.values(), key=lambda item: str(item.get("name", "")).lower())
        return {"count": len(packages), "packages": packages}

    # ----- signed platform updater -----

    @staticmethod
    def _validate_platform_target(target: str) -> None:
        if not target.startswith(PLATFORM_TARGET_ROOT):
            raise DeploymentError(
                f"Platform target is outside {PLATFORM_TARGET_ROOT}: {target}"
            )

    def validate_platform_update(
        self, package_name: str, current_version: str
    ) -> dict[str, Any]:
        package = self._archive_path(self.platform_updates, package_name)
        package_sha256 = self._sha256_file(package)
        with self._open_archive(package) as archive:
            self._validate_zip_metadata(archive)
            manifest, fingerprint = self._read_signed_metadata(
                archive, "platform_update", "platform"
            )
            if manifest.get("domain") != PLATFORM_DOMAIN:
                raise DeploymentError("Platform update domain does not match JNS.")
            from_version = manifest.get("from_version")
            if isinstance(from_version, str):
                allowed_from = [from_version]
            elif isinstance(from_version, list) and all(
                isinstance(item, str) for item in from_version
            ):
                allowed_from = from_version
            else:
                raise DeploymentError("Platform update requires from_version string or list.")
            if "*" not in allowed_from and current_version not in allowed_from:
                raise DeploymentError(
                    f"Platform update does not permit upgrade from {current_version}."
                )
            to_version = manifest.get("to_version")
            if not isinstance(to_version, str) or not to_version.strip():
                raise DeploymentError("Platform update requires to_version.")
            validated = self._validate_declared_files(
                archive, manifest, self._validate_platform_target
            )
            targets = {item.target_rel for item in validated}
            missing = sorted(PLATFORM_REQUIRED_TARGETS - targets)
            if missing:
                raise DeploymentError(
                    "Platform update is missing required integration files: "
                    + ", ".join(missing)
                )
            target_data = {
                entry["target"]: archive.read(entry["source"])
                for entry in manifest["files"]
            }
            for target, data in target_data.items():
                if target.endswith(".py"):
                    try:
                        compile(data.decode("utf-8"), target, "exec")
                    except (UnicodeDecodeError, SyntaxError) as exc:
                        raise DeploymentError(
                            f"Platform Python validation failed for {target}: {exc}"
                        ) from exc
            embedded_target = "custom_components/jns_deployment/manifest.json"
            try:
                embedded = json.loads(target_data[embedded_target].decode("utf-8"))
            except (KeyError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise DeploymentError("Platform update contains invalid integration manifest.") from exc
            if embedded.get("domain") != PLATFORM_DOMAIN:
                raise DeploymentError("Embedded integration manifest domain is incorrect.")
            if embedded.get("version") != to_version:
                raise DeploymentError("Embedded integration version does not match to_version.")
        return {
            "ok": True,
            "kind": "platform_update",
            "signed": True,
            "package": package_name,
            "package_sha256": package_sha256,
            "publisher_id": manifest["publisher_id"],
            "publisher_fingerprint_sha256": fingerprint,
            "name": manifest["name"],
            "version": manifest["version"],
            "from_version": allowed_from,
            "to_version": to_version,
            "file_count": len(validated),
            "files": [asdict(item) for item in validated],
        }

    def install_platform_update(
        self, package_name: str, current_version: str, dry_run: bool = False
    ) -> dict[str, Any]:
        with self._exclusive_operation():
            self._require_audit_integrity()
            validation = self.validate_platform_update(package_name, current_version)
            required = (
                sum(item["size"] for item in validation["files"])
                * 2
                + MIN_FREE_SPACE_RESERVE
            )
            if shutil.disk_usage(self.config_root).free < required:
                raise DeploymentError("Insufficient free disk space for safe platform update.")
            if dry_run:
                return {
                    **validation,
                    "dry_run": True,
                    "installed": False,
                    "requires_restart": True,
                }

            package = self._archive_path(self.platform_updates, package_name)
            transaction_id = (
                time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
                + "-platform-"
                + uuid.uuid4().hex[:8]
            )
            tx_root = (self.backups / transaction_id).resolve()
            tx_root.mkdir(parents=True, exist_ok=False)
            tx_path = tx_root / TRANSACTION_RECORD
            live_root = (
                self.config_root / "custom_components" / "jns_deployment"
            ).resolve()
            live_parent = live_root.parent
            stage_root = (live_parent / f".jns_stage_{transaction_id}").resolve()
            hold_root = (live_parent / f".jns_old_{transaction_id}").resolve()
            backup_tree = tx_root / "platform_backup" / "jns_deployment"
            for path in (stage_root, hold_root):
                if path.exists():
                    shutil.rmtree(path)
            transaction = {
                "transaction_id": transaction_id,
                "kind": "platform_update",
                "package": package_name,
                "package_sha256": validation["package_sha256"],
                "publisher_id": validation["publisher_id"],
                "publisher_fingerprint_sha256": validation["publisher_fingerprint_sha256"],
                "name": validation["name"],
                "from_version": current_version,
                "to_version": validation["to_version"],
                "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "status": "staging",
            }
            self._write_json_atomic(tx_path, transaction)
            self._audit(
                "platform_update_started",
                {
                    "transaction_id": transaction_id,
                    "from_version": current_version,
                    "to_version": validation["to_version"],
                    "publisher_id": validation["publisher_id"],
                    "package_sha256": validation["package_sha256"],
                },
            )
            try:
                stage_root.mkdir(parents=True, exist_ok=False)
                with self._open_archive(package) as archive:
                    self._validate_zip_metadata(archive)
                    manifest, _ = self._read_signed_metadata(
                        archive, "platform_update", "platform"
                    )
                    self._validate_declared_files(
                        archive, manifest, self._validate_platform_target
                    )
                    prefix = PurePosixPath(PLATFORM_TARGET_ROOT.rstrip("/"))
                    for entry in manifest["files"]:
                        target = self._safe_posix_path(entry["target"])
                        relative = PurePosixPath(target).relative_to(prefix)
                        destination = (stage_root / str(relative)).resolve()
                        if stage_root not in destination.parents:
                            raise DeploymentError(
                                "Platform staging path escaped staging root."
                            )
                        self._write_bytes_atomic(destination, archive.read(entry["source"]))
                        if self._sha256_file(destination) != entry["sha256"].lower():
                            raise DeploymentError(f"Platform staged hash mismatch: {target}")

                if not live_root.is_dir():
                    raise DeploymentError("Current JNS integration directory is missing.")
                backup_tree.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(live_root, backup_tree)
                self._fsync_dir(backup_tree.parent)
                transaction["status"] = "committing"
                transaction["backup_tree"] = str(backup_tree.relative_to(tx_root))
                self._write_json_atomic(tx_path, transaction)

                os.replace(live_root, hold_root)
                self._fsync_dir(live_parent)
                try:
                    os.replace(stage_root, live_root)
                    self._fsync_dir(live_parent)
                except Exception:
                    os.replace(hold_root, live_root)
                    self._fsync_dir(live_parent)
                    raise

                for item in validation["files"]:
                    live = (self.config_root / item["target_rel"]).resolve()
                    if not live.is_file():
                        raise DeploymentError(
                            f"Platform target missing after update: {item['target_rel']}"
                        )
                    if self._sha256_file(live) != item["sha256"]:
                        raise DeploymentError(
                            f"Platform post-commit hash mismatch: {item['target_rel']}"
                        )
                shutil.rmtree(hold_root, ignore_errors=True)
                transaction["status"] = "pending_restart"
                transaction["committed_utc"] = time.strftime(
                    "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
                )
                self._write_json_atomic(tx_path, transaction)
                pending = {
                    "transaction_id": transaction_id,
                    "from_version": current_version,
                    "to_version": validation["to_version"],
                    "status": "pending_restart",
                    "created_utc": transaction["created_utc"],
                }
                self._write_json_atomic(self.state / PENDING_PLATFORM_UPDATE, pending)
                recovery_text = (
                    "JNS PLATFORM UPDATE EMERGENCY RECOVERY\n\n"
                    f"Transaction: {transaction_id}\n"
                    f"From: {current_version}\n"
                    f"To: {validation['to_version']}\n\n"
                    "If the new integration cannot load after restart, use SSH:\n"
                    "python3 /config/jns/recovery/jns_emergency_recover.py "
                    f"--config /config --transaction {transaction_id}\n"
                    "Then restart Home Assistant.\n"
                )
                self._write_bytes_atomic(tx_root / "RECOVERY.txt", recovery_text.encode())
                self._audit(
                    "platform_update_pending_restart",
                    {
                        "transaction_id": transaction_id,
                        "from_version": current_version,
                        "to_version": validation["to_version"],
                    },
                )
                return {
                    "ok": True,
                    "kind": "platform_update",
                    "installed": True,
                    "dry_run": False,
                    "transaction_id": transaction_id,
                    "from_version": current_version,
                    "to_version": validation["to_version"],
                    "publisher_id": validation["publisher_id"],
                    "requires_restart": True,
                }
            except Exception as exc:
                try:
                    if hold_root.is_dir():
                        if live_root.exists():
                            shutil.rmtree(live_root)
                        os.replace(hold_root, live_root)
                        self._fsync_dir(live_parent)
                    elif backup_tree.is_dir() and not live_root.exists():
                        shutil.copytree(backup_tree, live_root)
                        self._fsync_dir(live_parent)
                finally:
                    shutil.rmtree(stage_root, ignore_errors=True)
                    transaction["status"] = "rolled_back_after_failure"
                    self._write_json_atomic(tx_path, transaction)
                    self._audit(
                        "platform_update_failed",
                        {"transaction_id": transaction_id, "error": str(exc)[:500]},
                    )
                raise
            finally:
                shutil.rmtree(stage_root, ignore_errors=True)

    def confirm_pending_platform_update(
        self, current_version: str
    ) -> dict[str, Any] | None:
        pending_path = self.state / PENDING_PLATFORM_UPDATE
        if not pending_path.is_file():
            return None
        try:
            pending = json.loads(pending_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        txid = pending.get("transaction_id")
        to_version = pending.get("to_version")
        if not isinstance(txid, str):
            return None
        if current_version == to_version:
            try:
                record = self._read_transaction(txid)
            except DeploymentError:
                return None
            record["status"] = "confirmed"
            record["confirmed_utc"] = time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
            )
            self._write_json_atomic(self._transaction_path(txid), record)
            pending["status"] = "confirmed"
            pending["confirmed_utc"] = record["confirmed_utc"]
            self._write_json_atomic(pending_path, pending)
            try:
                self._audit(
                    "platform_update_confirmed",
                    {"transaction_id": txid, "running_version": current_version},
                )
            except DeploymentError:
                pass
            return pending
        pending["status"] = "version_mismatch"
        pending["running_version"] = current_version
        self._write_json_atomic(pending_path, pending)
        return pending

    def rollback_platform_update(self, transaction_id: str) -> dict[str, Any]:
        with self._exclusive_operation():
            record = self._read_transaction(transaction_id)
            if record.get("kind") != "platform_update":
                raise DeploymentError("Transaction is not a platform update.")
            tx_root = self._transaction_path(transaction_id).parent
            backup_tree = (tx_root / "platform_backup" / "jns_deployment").resolve()
            if not backup_tree.is_dir():
                raise DeploymentError("Platform update backup tree is missing.")
            live_root = (
                self.config_root / "custom_components" / "jns_deployment"
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
                self._fsync_dir(live_parent)
            except Exception:
                if hold_root.exists() and not live_root.exists():
                    os.replace(hold_root, live_root)
                    self._fsync_dir(live_parent)
                raise
            shutil.rmtree(hold_root, ignore_errors=True)
            record["status"] = "platform_rolled_back"
            record["platform_rolled_back_utc"] = time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
            )
            self._write_json_atomic(self._transaction_path(transaction_id), record)
            (self.state / PENDING_PLATFORM_UPDATE).unlink(missing_ok=True)
            self._audit(
                "platform_update_rolled_back",
                {
                    "transaction_id": transaction_id,
                    "restored_version": record.get("from_version"),
                },
            )
            return {
                "ok": True,
                "transaction_id": transaction_id,
                "requires_restart": True,
                "restored_version": record.get("from_version"),
            }

    def install_recovery_tool(self, source: Path) -> dict[str, Any]:
        target = self.recovery_dir / "jns_emergency_recover.py"
        source_hash = self._sha256_file(source)
        if target.is_file() and self._sha256_file(target) == source_hash:
            return {"changed": False, "path": str(target), "sha256": source_hash}
        self._copy_file_durable(source, target)
        return {"changed": True, "path": str(target), "sha256": source_hash}
