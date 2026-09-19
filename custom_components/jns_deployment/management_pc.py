from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
from pathlib import Path
import re
import secrets
import time
from typing import Any

from aiohttp import web
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant

from .addon import (\n    SftpProvisioningError,\n    async_apply_management_keys,\n    async_disable_management_transport,\n    async_existing_authorized_keys,\n)
from .const import DOMAIN, DEFAULT_TRUST, TRUST_STORE_FILE

_LOGGER = logging.getLogger(__name__)

REGISTRY_REL = "jns/management/pcs.json"
SESSIONS_REL = "jns/management/enrollment_sessions.json"
SFTP_HOST_PUB_REL = "jns/sftp/server_host_ed25519.pub"
ENROLLMENT_TTL = 600
DEVICE_ID_RE = re.compile(r"^[a-f0-9-]{36}$")
PUBLISHER_ROLE = "jns-config-production"


def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp.replace(path)


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _openssh_fingerprint(line: str) -> str:
    parts = line.strip().split()
    if len(parts) < 2:
        raise ValueError("Invalid OpenSSH public key")
    raw = base64.b64decode(parts[1], validate=True)
    digest = hashlib.sha256(raw).digest()
    return "SHA256:" + base64.b64encode(digest).decode("ascii").rstrip("=")


def _normalize_code(code: str) -> str:
    return "".join(ch for ch in code.upper() if ch.isalnum())


class ManagementPCRegistry:
    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        config = Path(hass.config.path())
        self.registry_path = config / REGISTRY_REL
        self.sessions_path = config / SESSIONS_REL
        self.trust_path = config / DEFAULT_TRUST / TRUST_STORE_FILE
        self.sftp_host_pub_path = config / SFTP_HOST_PUB_REL
        self._lock = asyncio.Lock()

    def _load_registry(self) -> dict[str, Any]:
        if not self.registry_path.is_file():
            return {"schema": 1, "pcs": [], "legacy_sftp_keys": []}
        try:
            data = json.loads(self.registry_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"schema": 1, "pcs": [], "legacy_sftp_keys": []}
        if data.get("schema") != 1 or not isinstance(data.get("pcs"), list):
            return {"schema": 1, "pcs": [], "legacy_sftp_keys": []}
        if not isinstance(data.get("legacy_sftp_keys"), list):
            data["legacy_sftp_keys"] = []
        return data

    def _save_registry(self, data: dict[str, Any]) -> None:
        _atomic_write_json(self.registry_path, data)

    async def _async_load_registry(self) -> dict[str, Any]:
        return await self.hass.async_add_executor_job(self._load_registry)

    async def _async_save_registry(self, data: dict[str, Any]) -> None:
        await self.hass.async_add_executor_job(self._save_registry, data)

    def _load_sessions(self) -> dict[str, Any]:
        if not self.sessions_path.is_file():
            return {"schema": 1, "sessions": []}
        try:
            data = json.loads(self.sessions_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"schema": 1, "sessions": []}
        if data.get("schema") != 1 or not isinstance(data.get("sessions"), list):
            return {"schema": 1, "sessions": []}
        return data

    def _save_sessions(self, data: dict[str, Any]) -> None:
        _atomic_write_json(self.sessions_path, data)

    async def _async_load_sessions(self) -> dict[str, Any]:
        return await self.hass.async_add_executor_job(self._load_sessions)

    async def _async_save_sessions(self, data: dict[str, Any]) -> None:
        await self.hass.async_add_executor_job(self._save_sessions, data)

    async def create_enrollment_session(self) -> dict[str, Any]:
        async with self._lock:
            now = int(time.time())
            sessions = await self._async_load_sessions()
            sessions["sessions"] = [
                x for x in sessions["sessions"]
                if isinstance(x, dict) and int(x.get("expires_at", 0)) > now and not x.get("used")
            ]
            # 100 bits of capability entropy, grouped for human copy/paste.
            raw = base64.b32encode(secrets.token_bytes(13)).decode("ascii").rstrip("=")[:20]
            display = "-".join(raw[i:i+5] for i in range(0, len(raw), 5))
            digest = _sha256_hex(raw.encode("ascii"))
            expires = now + ENROLLMENT_TTL
            sessions["sessions"].append({
                "code_sha256": digest,
                "created_at": now,
                "expires_at": expires,
                "used": False,
            })
            await self._async_save_sessions(sessions)
            return {"code": display, "expires_at": expires, "ttl_seconds": ENROLLMENT_TTL}

    async def _consume_code(self, code: str) -> bool:
        normalized = _normalize_code(code)
        if len(normalized) != 20:
            return False
        digest = _sha256_hex(normalized.encode("ascii"))
        async with self._lock:
            now = int(time.time())
            sessions = await self._async_load_sessions()
            matched = False
            retained: list[dict[str, Any]] = []
            for item in sessions["sessions"]:
                if not isinstance(item, dict):
                    continue
                if int(item.get("expires_at", 0)) <= now or item.get("used"):
                    continue
                if not matched and hmac.compare_digest(str(item.get("code_sha256", "")), digest):
                    item["used"] = True
                    matched = True
                retained.append(item)
            sessions["sessions"] = retained
            await self._async_save_sessions(sessions)
            return matched

    @staticmethod
    def _validate_ssh_public_key(value: str) -> str:
        value = value.strip()
        if len(value) > 4096 or not value.startswith("ssh-ed25519 "):
            raise ValueError("JNS management PCs must use an Ed25519 OpenSSH key")
        try:
            key = serialization.load_ssh_public_key(value.encode("ascii"))
        except Exception as exc:
            raise ValueError("Invalid SSH public key") from exc
        if not isinstance(key, Ed25519PublicKey):
            raise ValueError("SSH public key must be Ed25519")
        return value

    @staticmethod
    def _validate_signing_public_key(value: str) -> tuple[str, str]:
        try:
            raw = base64.b64decode(value, validate=True)
        except Exception as exc:
            raise ValueError("Invalid signing public key") from exc
        if len(raw) != 32:
            raise ValueError("Ed25519 signing public key must be 32 bytes")
        Ed25519PublicKey.from_public_bytes(raw)
        return value, _sha256_hex(raw)

    def _load_trust_json(self) -> dict[str, Any]:
        if not self.trust_path.is_file():
            return {"schema": 1, "publishers": []}
        data = json.loads(self.trust_path.read_text(encoding="utf-8"))
        if data.get("schema") != 1 or not isinstance(data.get("publishers"), list):
            raise ValueError("JNS trust store has an unsupported format")
        return data

    def _upsert_publisher(self, publisher: dict[str, Any]) -> None:
        data = self._load_trust_json()
        pid = publisher["id"]
        records = [p for p in data["publishers"] if isinstance(p, dict) and p.get("id") != pid]
        records.append(publisher)
        records.sort(key=lambda x: str(x.get("id", "")))
        data["publishers"] = records
        self.trust_path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write_json(self.trust_path, data)

    def _remove_publisher(self, publisher_id: str) -> None:
        if not self.trust_path.is_file():
            return
        data = self._load_trust_json()
        data["publishers"] = [
            p for p in data["publishers"]
            if not (isinstance(p, dict) and p.get("id") == publisher_id)
        ]
        _atomic_write_json(self.trust_path, data)

    async def _async_load_trust_json(self) -> dict[str, Any]:
        return await self.hass.async_add_executor_job(self._load_trust_json)

    async def _async_upsert_publisher(self, publisher: dict[str, Any]) -> None:
        await self.hass.async_add_executor_job(self._upsert_publisher, publisher)

    async def _async_remove_publisher(self, publisher_id: str) -> None:
        await self.hass.async_add_executor_job(self._remove_publisher, publisher_id)

    async def _sync_sftp_authorized_keys(self, registry: dict[str, Any], *, capture_existing: bool = False) -> dict[str, Any]:
        existing = await async_existing_authorized_keys(self.hass) if capture_existing else []
        known = {
            str(pc.get("ssh_public_key", "")).strip()
            for pc in registry.get("pcs", [])
            if isinstance(pc, dict) and pc.get("status", "active") == "active"
        }
        legacy = list(registry.get("legacy_sftp_keys", []))
        for key in existing:
            if key not in known and key not in legacy:
                legacy.append(key)
        registry["legacy_sftp_keys"] = legacy
        active = sorted({*known, *legacy})
        if active:
            await async_apply_management_keys(self.hass, active)
        else:
            # Fail closed: revoking the final key must not leave a stale
            # authorized_keys entry active inside a still-running SFTP app.
            await async_disable_management_transport(self.hass)
        return registry

    def _sftp_server_identity(self) -> dict[str, str]:
        if not self.sftp_host_pub_path.is_file():
            return {"public_key": "", "fingerprint": ""}
        line = self.sftp_host_pub_path.read_text(encoding="utf-8").strip()
        try:
            fp = _openssh_fingerprint(line)
        except Exception:
            return {"public_key": "", "fingerprint": ""}
        return {"public_key": line, "fingerprint": fp}

    async def _async_sftp_server_identity(self) -> dict[str, str]:
        return await self.hass.async_add_executor_job(self._sftp_server_identity)

    async def ensure_transport_policy(self) -> dict[str, Any]:
        """Preserve pre-v5.5 authorized keys and enforce key-only transport when keys exist."""
        async with self._lock:
            registry = await self._async_load_registry()
            registry = await self._sync_sftp_authorized_keys(registry, capture_existing=True)
            await self._async_save_registry(registry)
            active_count = sum(
                1 for pc in registry.get("pcs", [])
                if isinstance(pc, dict) and pc.get("status") == "active" and pc.get("ssh_public_key")
            )
            return {
                "mode": "publickey" if active_count or registry.get("legacy_sftp_keys") else "unconfigured",
                "active_pc_keys": active_count,
                "legacy_keys": len(registry.get("legacy_sftp_keys", [])),
            }

    async def enroll(self, payload: dict[str, Any], remote_ip: str | None) -> dict[str, Any]:
        code = str(payload.get("code", ""))
        if not await self._consume_code(code):
            raise ValueError("Enrollment code is invalid, expired or already used")

        device_id = str(payload.get("device_id", "")).strip().lower()
        if not DEVICE_ID_RE.fullmatch(device_id):
            raise ValueError("Invalid management PC id")
        device_name = str(payload.get("device_name", "")).strip()[:80]
        if not device_name:
            raise ValueError("Management PC name is required")
        ssh_public = self._validate_ssh_public_key(str(payload.get("ssh_public_key", "")))
        signing_b64, signing_fp = self._validate_signing_public_key(str(payload.get("signing_public_key", "")))
        publisher_id = f"{PUBLISHER_ROLE}.{device_id.replace('-', '')[:12]}"

        async with self._lock:
            registry = await self._async_load_registry()
            existing_pc = next((
                pc for pc in registry["pcs"]
                if isinstance(pc, dict) and pc.get("device_id") == device_id and pc.get("status") == "active"
            ), None)
            old_user = None
            if existing_pc is not None:
                if (str(existing_pc.get("ssh_public_key", "")).strip() != ssh_public or
                        str(existing_pc.get("signing_public_key", "")).strip() != signing_b64):
                    raise ValueError("This management PC id is already enrolled with different public keys")
                # Keep the existing HA identity valid until replacement
                # enrollment has completed. This prevents a failed retry from
                # invalidating an already-enrolled management PC.
                old_user_id = existing_pc.get("ha_user_id")
                if old_user_id:
                    old_user = await self.hass.auth.async_get_user(str(old_user_id))

            user = await self.hass.auth.async_create_system_user(
                f"JNS Management PC - {device_name}", local_only=True
            )
            refresh = await self.hass.auth.async_create_refresh_token(user)
            access = self.hass.auth.async_create_access_token(refresh, remote_ip)

            try:
                record = {
                    "device_id": device_id,
                    "device_name": device_name,
                    "status": "active",
                    "created_at": int(time.time()),
                    "commissioned_at": None,
                    "ha_user_id": user.id,
                    "refresh_token_id": refresh.id,
                    "ssh_public_key": ssh_public,
                    "ssh_fingerprint": _openssh_fingerprint(ssh_public),
                    "publisher_role": PUBLISHER_ROLE,
                    "publisher_id": publisher_id,
                    "signing_public_key": signing_b64,
                    "signing_fingerprint_sha256": signing_fp,
                }
                registry["pcs"] = [
                    pc for pc in registry["pcs"]
                    if not (isinstance(pc, dict) and pc.get("device_id") == device_id)
                ] + [record]
                registry = await self._sync_sftp_authorized_keys(registry, capture_existing=True)
                await self._async_save_registry(registry)
                await self._async_upsert_publisher({
                    "id": publisher_id,
                    "name": f"JNS Config Production - {device_name}",
                    "public_key": signing_b64,
                    "fingerprint_sha256": signing_fp,
                    "scopes": ["config"],
                    "enabled": True,
                    "management_pc_id": device_id,
                })
            except Exception:
                # A failed enrollment must not leave a usable orphan token
                # identity behind. The single-use enrollment capability remains
                # consumed, so the administrator must explicitly issue a fresh
                # code before retrying.
                try:
                    await self.hass.auth.async_remove_user(user)
                except Exception:
                    _LOGGER.exception("Failed to remove incomplete JNS management PC identity")
                raise

            if old_user is not None and old_user.id != user.id:
                try:
                    await self.hass.auth.async_remove_user(old_user)
                except Exception:
                    _LOGGER.exception("Failed to retire previous JNS management PC identity")

        # The app may have restarted while applying the key. Give it a short
        # window to export its stable host public key to the shared JNS area.
        identity = {"public_key": "", "fingerprint": ""}
        for _ in range(20):
            identity = await self._async_sftp_server_identity()
            if identity["fingerprint"]:
                break
            await asyncio.sleep(0.25)

        return {
            "device_id": device_id,
            "device_name": device_name,
            "publisher_id": publisher_id,
            "publisher_role": PUBLISHER_ROLE,
            "signing_fingerprint_sha256": signing_fp,
            "sftp_username": "jnstransfer",
            "sftp_port": 2222,
            "sftp_host_public_key": identity["public_key"],
            "sftp_host_fingerprint": identity["fingerprint"],
            "access_token": access,
            "access_token_expires_in": int(refresh.access_token_expiration.total_seconds()),
            "refresh_token": refresh.token,
        }

    async def list_pcs(self) -> dict[str, Any]:
        data = await self._async_load_registry()
        pcs = []
        for pc in data.get("pcs", []):
            if not isinstance(pc, dict):
                continue
            pcs.append({
                key: pc.get(key)
                for key in (
                    "device_id", "device_name", "status", "created_at", "commissioned_at",
                    "ssh_fingerprint", "publisher_role", "publisher_id", "signing_fingerprint_sha256",
                )
            })
        trust_data = await self._async_load_trust_json()
        return {
            "count": len(pcs),
            "pcs": pcs,
            "legacy_sftp_key_count": len(data.get("legacy_sftp_keys", [])),
            "legacy_publisher_present": any(
                isinstance(p, dict) and p.get("id") == PUBLISHER_ROLE
                for p in trust_data.get("publishers", [])
            ),
        }

    async def require_admin(self, user_id: str | None) -> None:
        if not user_id:
            raise PermissionError("Authenticated administrator required")
        user = await self.hass.auth.async_get_user(user_id)
        if user is None or not user.is_admin:
            raise PermissionError("Home Assistant administrator approval required")

    async def require_write_authorized(self, user_id: str | None) -> None:
        if not user_id:
            raise PermissionError("Authenticated JNS management identity required")
        user = await self.hass.auth.async_get_user(user_id)
        if user is not None and user.is_admin:
            return
        registry = await self._async_load_registry()
        if any(
            isinstance(pc, dict)
            and pc.get("status") == "active"
            and pc.get("ha_user_id") == user_id
            for pc in registry.get("pcs", [])
        ):
            return
        raise PermissionError("This Home Assistant identity is not an enrolled JNS management PC")

    async def mark_commissioned(self, user_id: str | None) -> dict[str, Any]:
        if not user_id:
            raise PermissionError("Authenticated JNS management identity required")
        async with self._lock:
            registry = await self._async_load_registry()
            matched = None
            for pc in registry.get("pcs", []):
                if isinstance(pc, dict) and pc.get("status") == "active" and pc.get("ha_user_id") == user_id:
                    pc["commissioned_at"] = int(time.time())
                    matched = pc
                    break
            if not matched:
                raise PermissionError("Caller is not an enrolled JNS management PC")
            await self._async_save_registry(registry)
            return {"device_id": matched["device_id"], "commissioned": True, "commissioned_at": matched["commissioned_at"]}

    async def revoke_pc(self, device_id: str) -> dict[str, Any]:
        async with self._lock:
            registry = await self._async_load_registry()
            target = next((pc for pc in registry.get("pcs", []) if isinstance(pc, dict) and pc.get("device_id") == device_id), None)
            if not target:
                raise ValueError("Unknown management PC")
            target["status"] = "revoked"
            user_id = target.get("ha_user_id")
            publisher_id = str(target.get("publisher_id", ""))
            if user_id:
                user = await self.hass.auth.async_get_user(str(user_id))
                if user is not None:
                    await self.hass.auth.async_remove_user(user)
            if publisher_id:
                await self._async_remove_publisher(publisher_id)
            registry = await self._sync_sftp_authorized_keys(registry)
            await self._async_save_registry(registry)
            return {"device_id": device_id, "revoked": True}

    async def revoke_legacy(self) -> dict[str, Any]:
        async with self._lock:
            registry = await self._async_load_registry()
            commissioned = [
                pc for pc in registry.get("pcs", [])
                if isinstance(pc, dict) and pc.get("status") == "active" and pc.get("commissioned_at")
            ]
            if not commissioned:
                raise ValueError("Legacy credentials cannot be revoked until at least one enrolled PC is commissioned")
            removed_keys = len(registry.get("legacy_sftp_keys", []))
            registry["legacy_sftp_keys"] = []
            registry = await self._sync_sftp_authorized_keys(registry)
            await self._async_save_registry(registry)
            await self._async_remove_publisher(PUBLISHER_ROLE)
            return {"legacy_sftp_keys_removed": removed_keys, "legacy_publisher_removed": True}


class EnrollmentView(HomeAssistantView):
    url = "/api/jns_deployment/enroll"
    name = "api:jns_deployment:enroll"
    requires_auth = False

    def __init__(self, registry: ManagementPCRegistry) -> None:
        self.registry = registry

    async def post(self, request: web.Request) -> web.Response:
        try:
            if request.content_length and request.content_length > 16384:
                return self.json({"error": "request_too_large"}, status_code=413)
            payload = await request.json()
            if not isinstance(payload, dict):
                raise ValueError("JSON object required")
            result = await self.registry.enroll(payload, request.remote)
            return self.json(result, headers={"Cache-Control": "no-store", "Pragma": "no-cache"})
        except ValueError as exc:
            _LOGGER.warning("JNS management PC enrollment rejected: %s", exc)
            return self.json({"error": str(exc)}, status_code=400, headers={"Cache-Control": "no-store"})
        except SftpProvisioningError as exc:
            _LOGGER.error(
                "JNS management PC enrollment transport stage failed: %s: %s",
                exc.stage,
                exc.detail,
            )
            return self.json(
                {"error": f"{exc.stage}: {exc.detail}"},
                status_code=503,
                headers={"Cache-Control": "no-store"},
            )
        except Exception:
            _LOGGER.exception("JNS management PC enrollment failed")
            return self.json({"error": "enrollment_failed"}, status_code=500, headers={"Cache-Control": "no-store"})
