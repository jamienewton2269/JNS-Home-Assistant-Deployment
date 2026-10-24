#!/usr/bin/env python3
"""JNS HA Steward: narrowly scoped local HA-General automation reload.
Run inside HA-General Core container via the existing Proxmox guest agent.
No network token transfer: secret is loaded only from this container's /config.
This is NOT an HTTP server and never accepts a URL or arbitrary service name.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import time
import urllib.error
import urllib.request

ROOT = Path("/config/.jns-steward")
TOKEN_FILE = ROOT / "ha_general_api.token"
AUDIT_FILE = ROOT / "ha_reload_audit.jsonl"
AUTOMATIONS = Path("/config/automations.yaml")
PACKAGE = Path("/config/packages/jns_lux_manual_off_v1.yaml")
API_BASE = "http://127.0.0.1/api"  # Loopback only; never send token on the LAN.
ENTITY_IDS = (
    "automation.jns_lux_remember_manual_off_until_sunrise",
    "automation.general_shared_lux_progressive_control",
)
HEX64 = re.compile(r"[0-9a-f]{64}\Z")


class GuardError(RuntimeError):
    pass


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def locked_root() -> bool:
    if ROOT.is_symlink() or not ROOT.is_dir():
        return False
    st = ROOT.stat()
    return st.st_uid == 0 and stat.S_IMODE(st.st_mode) == 0o700


def safe_token() -> str:
    if os.geteuid() != 0:
        raise GuardError("must run as root inside HA-General")
    if not locked_root():
        raise GuardError("missing or insecure Steward credential directory")
    if TOKEN_FILE.is_symlink() or not TOKEN_FILE.is_file():
        raise GuardError("admin token has not been installed locally")
    st = TOKEN_FILE.stat()
    if st.st_uid != 0 or stat.S_IMODE(st.st_mode) != 0o600:
        raise GuardError("token ownership or permissions are not 0600 root")
    if st.st_size < 64 or st.st_size > 1024:
        raise GuardError("admin token format invalid")
    token = TOKEN_FILE.read_text(encoding="utf-8").strip()
    if not 64 <= len(token) <= 1024 or any(c.isspace() for c in token):
        raise GuardError("admin token contains invalid characters")
    return token


def audit(action: str, outcome: str) -> None:
    if not locked_root():
        return
    obj = {
        "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "capability": "jns.ha_general.automation_reload",
        "action": action,
        "outcome": outcome,
    }
    flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(AUDIT_FILE, flags, 0o600)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(obj, sort_keys=True) + "\n")
    except BaseException:
        os.close(fd)
        raise


def api(token: str, *, method: str, action: str, body: bytes | None = None) -> tuple[int, bytes]:
    # Never expose an arbitrary URL/path from the CLI.
    assert action in ("health", "reload", *ENTITY_IDS)
    if action == "health":
        path = "/"
    elif action == "reload":
        path = "/services/automation/reload"
    else:
        path = "/states/" + action
    if (method, action) not in (
        ("GET", "health"), ("POST", "reload"),
        *(("GET", entity) for entity in ENTITY_IDS),
    ):
        raise GuardError("operation not allowed")
    headers = {"Authorization": "Bearer " + token, "Accept": "application/json"}
    if method == "POST":
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(API_BASE + path, data=body, method=method, headers=headers)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=12 if method == "GET" else 55) as resp:
            return resp.status, resp.read(16384)
    except urllib.error.HTTPError as exc:
        raise GuardError(f"Home Assistant API rejected operation: HTTP {exc.code}") from None
    except urllib.error.URLError:
        raise GuardError("Home Assistant loopback API is unavailable") from None


def hashes_guard(expected_auto: str, expected_pkg: str) -> None:
    if not HEX64.fullmatch(expected_auto) or not HEX64.fullmatch(expected_pkg):
        raise GuardError("invalid expected SHA-256 arguments")
    if file_hash(AUTOMATIONS) != expected_auto or file_hash(PACKAGE) != expected_pkg:
        raise GuardError("configuration changed after validation; reload refused")


def main() -> None:
    parser = argparse.ArgumentParser(description="JNS Steward one-purpose HA reload capability")
    parser.add_argument("mode", choices=("status", "probe", "reload"))
    parser.add_argument("--automations-sha")
    parser.add_argument("--package-sha")
    args = parser.parse_args()
    if os.geteuid() != 0 or not locked_root():
        raise GuardError("Steward capability not securely installed")
    if args.mode == "status":
        print(json.dumps({
            "installed": True, "token_present": TOKEN_FILE.is_file(),
            "capability": "jns.ha_general.automation_reload",
            "transport": "HA Core loopback",
        }, sort_keys=True))
        return
    token = safe_token()
    status, _ = api(token, method="GET", action="health")
    if status != 200:
        raise GuardError("authenticated API health check failed")
    if args.mode == "probe":
        audit("probe", "ok")
        print("JNS_STEWARD_HA_API_PROBE_OK")
        return
    if not args.automations_sha or not args.package_sha:
        raise GuardError("reload requires both expected file SHA-256 hashes")
    hashes_guard(args.automations_sha, args.package_sha)
    try:
        status, _ = api(token, method="POST", action="reload", body=b"{}")
        if status not in (200, 201):
            raise GuardError("Home Assistant did not accept automation reload")
        for entity in ENTITY_IDS:
            code, payload = api(token, method="GET", action=entity)
            data = json.loads(payload)
            if code != 200 or data.get("entity_id") != entity or data.get("state") not in ("on", "off"):
                raise GuardError("expected automation was not registered after reload")
        audit("reload", "verified")
        print("JNS_STEWARD_HA_AUTOMATIONS_RELOADED_AND_VERIFIED")
    except BaseException:
        audit("reload", "unconfirmed")
        raise


if __name__ == "__main__":
    try:
        main()
    except (GuardError, OSError, ValueError, json.JSONDecodeError) as exc:
        print("JNS_STEWARD_CAPABILITY_BLOCKED: " + str(exc)[:160], file=sys.stderr)
        sys.exit(2)
