from __future__ import annotations

import asyncio
import base64
from datetime import timedelta
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "custom_components" / "jns_deployment" / "management_pc.py"

# Minimal Home Assistant module stubs so the enrollment registry can be tested
# without installing the complete Home Assistant runtime in this build host.
ha = types.ModuleType("homeassistant")
ha_components = types.ModuleType("homeassistant.components")
ha_http = types.ModuleType("homeassistant.components.http")
ha_core = types.ModuleType("homeassistant.core")
class HomeAssistantView:
    pass
class HomeAssistant:
    pass
ha_http.HomeAssistantView = HomeAssistantView
ha_core.HomeAssistant = HomeAssistant
sys.modules.update({
    "homeassistant": ha,
    "homeassistant.components": ha_components,
    "homeassistant.components.http": ha_http,
    "homeassistant.core": ha_core,
})

pkg_name = "_jns_management_pc_test"
pkg = types.ModuleType(pkg_name)
pkg.__path__ = [str(SOURCE.parent)]
sys.modules[pkg_name] = pkg

applied_key_sets: list[list[str]] = []
disabled_count = 0
legacy_key_holder: list[str] = []

async def async_existing_authorized_keys(_hass):
    return list(legacy_key_holder)

async def async_apply_management_keys(_hass, keys):
    applied_key_sets.append(list(keys))
    return types.SimpleNamespace()

async def async_disable_management_transport(_hass):
    global disabled_count
    disabled_count += 1
    return {"running": False, "authorized_key_count": 0}

addon = types.ModuleType(pkg_name + ".addon")
addon.async_existing_authorized_keys = async_existing_authorized_keys
addon.async_apply_management_keys = async_apply_management_keys
addon.async_disable_management_transport = async_disable_management_transport
sys.modules[pkg_name + ".addon"] = addon

const = types.ModuleType(pkg_name + ".const")
const.DOMAIN = "jns_deployment"
const.DEFAULT_TRUST = "jns/trust"
const.TRUST_STORE_FILE = "publishers.json"
sys.modules[pkg_name + ".const"] = const

spec = importlib.util.spec_from_file_location(pkg_name + ".management_pc", SOURCE)
mod = importlib.util.module_from_spec(spec)
sys.modules[pkg_name + ".management_pc"] = mod
assert spec.loader is not None
spec.loader.exec_module(mod)
ManagementPCRegistry = mod.ManagementPCRegistry

class FakeConfig:
    def __init__(self, root: Path): self.root = root
    def path(self): return str(self.root)

class FakeUser:
    def __init__(self, uid: str, name: str, is_admin: bool = False):
        self.id = uid; self.name = name; self.is_admin = is_admin

class FakeRefresh:
    def __init__(self, rid: str, token: str):
        self.id = rid
        self.token = token
        self.access_token_expiration = timedelta(minutes=30)

class FakeAuth:
    def __init__(self):
        self.users: dict[str, FakeUser] = {"admin": FakeUser("admin", "Admin", True)}
        self.next_user = 1
        self.next_refresh = 1
        self.removed: list[str] = []
    async def async_create_system_user(self, name, local_only=True):
        assert local_only is True
        uid = f"pc-user-{self.next_user}"; self.next_user += 1
        user = FakeUser(uid, name, False); self.users[uid] = user; return user
    async def async_create_refresh_token(self, user):
        rid = f"refresh-{self.next_refresh}"; self.next_refresh += 1
        return FakeRefresh(rid, f"refresh-token-{rid}")
    def async_create_access_token(self, refresh, remote_ip):
        return f"access-for-{refresh.id}-{remote_ip or 'none'}"
    async def async_get_user(self, user_id):
        return self.users.get(user_id)
    async def async_remove_user(self, user):
        self.removed.append(user.id); self.users.pop(user.id, None)

class FakeHass:
    def __init__(self, root):
        self.config = FakeConfig(root)
        self.auth = FakeAuth()

def ssh_pair():
    key = Ed25519PrivateKey.generate()
    pub = key.public_key().public_bytes(serialization.Encoding.OpenSSH, serialization.PublicFormat.OpenSSH).decode("ascii")
    return key, pub

def signing_pub():
    key = Ed25519PrivateKey.generate()
    raw = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return key, base64.b64encode(raw).decode("ascii")

async def main():
    global legacy_key_holder, disabled_count
    with tempfile.TemporaryDirectory(prefix="jns-v55-enroll-test-") as td:
        root = Path(td)
        trust = root / "jns" / "trust" / "publishers.json"
        trust.parent.mkdir(parents=True)
        trust.write_text(json.dumps({"schema":1,"publishers":[{
            "id":"jns-config-production","name":"Legacy Production","public_key":"legacy","fingerprint_sha256":"legacy","scopes":["config"],"enabled":True
        }]}) + "\n", encoding="utf-8")

        # Export a stable server public key so enrollment response can pin it.
        _, server_pub = ssh_pair()
        host_pub = root / "jns" / "sftp" / "server_host_ed25519.pub"
        host_pub.parent.mkdir(parents=True)
        host_pub.write_text(server_pub + "\n", encoding="utf-8")

        _, legacy_pub = ssh_pair()
        legacy_key_holder = [legacy_pub]
        hass = FakeHass(root)
        registry = ManagementPCRegistry(hass)

        session = await registry.create_enrollment_session()
        raw_code = session["code"].replace("-", "")
        assert len(raw_code) == 20
        sessions_text = registry.sessions_path.read_text(encoding="utf-8")
        assert raw_code not in sessions_text, "plaintext enrollment code must never be persisted"
        assert "code_sha256" in sessions_text

        _, ssh_pub = ssh_pair(); _, sign_pub = signing_pub()
        payload = {
            "code": session["code"],
            "device_id": "01234567-89ab-cdef-0123-456789abcdef",
            "device_name": "NEW-MGMT-PC",
            "ssh_public_key": ssh_pub,
            "signing_public_key": sign_pub,
        }
        enrolled = await registry.enroll(payload, "10.10.10.55")
        assert enrolled["publisher_id"] == "jns-config-production.0123456789ab"
        assert enrolled["refresh_token"].startswith("refresh-token-")
        assert enrolled["access_token_expires_in"] == 1800
        assert enrolled["sftp_host_fingerprint"].startswith("SHA256:")

        # One-time capability must not be reusable.
        try:
            await registry.enroll(payload, "10.10.10.55")
        except ValueError as exc:
            assert "invalid, expired or already used" in str(exc)
        else:
            raise AssertionError("single-use enrollment code was accepted twice")

        state = await registry.list_pcs()
        assert state["count"] == 1
        assert state["legacy_sftp_key_count"] == 1
        assert state["legacy_publisher_present"] is True
        assert set(applied_key_sets[-1]) == {legacy_pub, ssh_pub}

        pc_user_id = json.loads(registry.registry_path.read_text())["pcs"][0]["ha_user_id"]
        await registry.require_write_authorized(pc_user_id)
        commissioned = await registry.mark_commissioned(pc_user_id)
        assert commissioned["commissioned"] is True

        # Legacy credentials can be removed only after the new PC is commissioned.
        legacy_result = await registry.revoke_legacy()
        assert legacy_result["legacy_sftp_keys_removed"] == 1
        state = await registry.list_pcs()
        assert state["legacy_sftp_key_count"] == 0
        assert state["legacy_publisher_present"] is False
        assert applied_key_sets[-1] == [ssh_pub]

        # Revoking the final PC must fail closed: its HA identity and publisher
        # disappear and SFTP is cleared/stopped instead of retaining a stale key.
        revoked = await registry.revoke_pc(payload["device_id"])
        assert revoked["revoked"] is True
        assert pc_user_id in hass.auth.removed
        assert disabled_count >= 1, "final credential revoke must disable SFTP transport"
        state = await registry.list_pcs()
        assert state["pcs"][0]["status"] == "revoked"
        trust_data = json.loads(trust.read_text())
        assert all(p.get("id") != enrolled["publisher_id"] for p in trust_data["publishers"])

    print("JNS v5.5.1 management-PC enrollment security self-test: PASS")

asyncio.run(main())
