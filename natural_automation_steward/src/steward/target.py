from __future__ import annotations

from dataclasses import dataclass
import base64
import json
import os
import socket
import subprocess
import time
from typing import Sequence


class TargetResolutionError(RuntimeError):
    pass


class GuestExecutionError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class HATarget:
    role: str
    host: str
    vmid: int
    name: str
    local: bool


def parse_qm_list(text: str) -> list[tuple[int, str, str]]:
    rows: list[tuple[int, str, str]] = []
    for line in text.splitlines():
        parts = line.split()
        if not parts or parts[0].upper() == "VMID":
            continue
        try:
            vmid = int(parts[0])
        except (ValueError, IndexError):
            continue
        name = parts[1] if len(parts) > 1 else ""
        status = parts[2] if len(parts) > 2 else ""
        rows.append((vmid, name, status))
    return rows


class TargetResolver:
    """Resolve HA-General by role/name, never by a fixed physical node."""

    def __init__(self, *, cache_seconds: float = 15.0):
        self.role = os.environ.get("NA_TARGET_ROLE", "ha-general").strip() or "ha-general"
        self.names = tuple(
            x.strip()
            for x in os.environ.get(
                "NA_TARGET_NAMES", "ha-s2-general,ha-general"
            ).split(",")
            if x.strip()
        )
        self.hosts = tuple(
            x.strip()
            for x in os.environ.get(
                "NA_PROXMOX_HOSTS",
                "nodea.home.arpa,nodeb.home.arpa,nodec.home.arpa,"
                "node-a.home.arpa,node-b.home.arpa,node-c.home.arpa",
            ).split(",")
            if x.strip()
        )

        # Permanent LXC deployment transport. When configured, this takes
        # precedence over direct qm/SSH access. The remote account is forced
        # through the root-owned HA Steward Proxmox wrapper.
        self.bridge_host = os.environ.get("NA_PVE_BRIDGE_HOST", "").strip()
        self.bridge_user = os.environ.get(
            "NA_PVE_BRIDGE_USER", "ha-steward-mgr"
        ).strip()
        self.bridge_key = os.environ.get(
            "NA_PVE_BRIDGE_KEY", "/etc/natural-automation/pve-bridge.key"
        ).strip()

        self.cache_seconds = cache_seconds
        self._cached: HATarget | None = None
        self._cached_at = 0.0

    @staticmethod
    def _local_names() -> set[str]:
        values = {socket.gethostname(), socket.getfqdn(), "localhost"}
        return {x.lower().split(".", 1)[0] for x in values if x}

    def _run_local(self, args: Sequence[str], timeout: float = 15.0) -> str:
        p = subprocess.run(
            list(args),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if p.returncode != 0:
            raise TargetResolutionError(
                (p.stderr or p.stdout or "command failed").strip()
            )
        return p.stdout

    def _run_remote(
        self, host: str, args: Sequence[str], timeout: float = 15.0
    ) -> str:
        cmd = [
            "ssh",
            "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=5",
            "-o", "StrictHostKeyChecking=accept-new",
            f"root@{host}",
            *args,
        ]
        p = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if p.returncode != 0:
            raise TargetResolutionError(
                (p.stderr or p.stdout or f"{host}: command failed").strip()
            )
        return p.stdout

    def _run_bridge(
        self, args: Sequence[str], timeout: float = 30.0
    ) -> str:
        if not self.bridge_host:
            raise TargetResolutionError("Proxmox bridge host is not configured")
        cmd = [
            "ssh",
            "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=5",
            "-o", "StrictHostKeyChecking=accept-new",
            "-o", "IdentitiesOnly=yes",
            "-i", self.bridge_key,
            f"{self.bridge_user}@{self.bridge_host}",
            *args,
        ]
        p = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if p.returncode != 0:
            raise TargetResolutionError(
                (p.stderr or p.stdout or "restricted Proxmox bridge failed").strip()
            )
        return p.stdout

    def _match(self, host: str, text: str, *, local: bool) -> HATarget | None:
        by_name = {name.lower(): name for name in self.names}
        for vmid, name, _status in parse_qm_list(text):
            if name.lower() in by_name:
                return HATarget(self.role, host, vmid, name, local)
        return None

    def _resolve_bridge(self) -> HATarget:
        raw = self._run_bridge(["status"], timeout=15.0)
        try:
            data = json.loads(raw)
            target = HATarget(
                role=str(data["role"]),
                host=str(data["host"]),
                vmid=int(data["vmid"]),
                name=str(data["name"]),
                local=False,
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise TargetResolutionError(
                f"Invalid restricted bridge status: {raw[:300]}"
            ) from exc
        if target.role != self.role or target.name not in self.names:
            raise TargetResolutionError(
                f"Restricted bridge resolved unexpected target {target}"
            )
        return target

    def resolve(self, *, refresh: bool = False) -> HATarget:
        now = time.monotonic()
        if (
            not refresh
            and self._cached
            and now - self._cached_at < self.cache_seconds
        ):
            return self._cached

        if self.bridge_host:
            found = self._resolve_bridge()
            self._cached, self._cached_at = found, now
            return found

        errors: list[str] = []
        local_host = socket.gethostname()

        try:
            found = self._match(
                local_host, self._run_local(["qm", "list"]), local=True
            )
            if found:
                self._cached, self._cached_at = found, now
                return found
        except Exception as exc:
            errors.append(f"{local_host}: {exc}")

        local_short = self._local_names()
        for host in self.hosts:
            if host.lower().split(".", 1)[0] in local_short:
                continue
            try:
                found = self._match(
                    host, self._run_remote(host, ["qm", "list"]), local=False
                )
                if found:
                    self._cached, self._cached_at = found, now
                    return found
            except Exception as exc:
                errors.append(f"{host}: {exc}")

        detail = "; ".join(errors[-4:])
        raise TargetResolutionError(
            f"Unable to resolve role {self.role!r} using VM names {self.names!r}"
            + (f": {detail}" if detail else "")
        )

    def _qm(self, target: HATarget, args: Sequence[str], timeout: float) -> str:
        cmd = ["qm", *args]
        if target.local:
            return self._run_local(cmd, timeout=timeout)
        return self._run_remote(target.host, cmd, timeout=timeout)

    @staticmethod
    def _decode_guest_result(raw: str) -> dict:
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise GuestExecutionError(
                f"Invalid qemu guest-agent response: {raw[:300]}"
            ) from exc

    def _bridge_guest_exec(
        self, argv: Sequence[str], *, timeout: float
    ) -> dict:
        payload = base64.urlsafe_b64encode(
            json.dumps(list(argv), separators=(",", ":")).encode()
        ).decode().rstrip("=")

        raw = self._run_bridge(
            ["guest-exec", payload],
            timeout=min(timeout, 45.0),
        )
        result = self._decode_guest_result(raw)

        pid = result.get("pid")
        if pid is not None and not result.get("exited"):
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                time.sleep(0.5)
                status_raw = self._run_bridge(
                    ["guest-exec-status", str(int(pid))],
                    timeout=15.0,
                )
                status = self._decode_guest_result(status_raw)
                if status.get("exited"):
                    result = status
                    break
            else:
                raise GuestExecutionError(
                    f"Guest command timed out after {timeout:.0f}s (pid {pid})"
                )

        if result.get("exitcode", 0) != 0:
            raise GuestExecutionError(
                (
                    result.get("err-data")
                    or result.get("out-data")
                    or "guest command failed"
                ).strip()
            )
        return result

    def guest_exec(
        self, argv: Sequence[str], *, timeout: float = 180.0
    ) -> dict:
        if self.bridge_host:
            self.resolve()
            return self._bridge_guest_exec(argv, timeout=timeout)

        target = self.resolve()
        raw = self._qm(
            target,
            ["guest", "exec", str(target.vmid), "--", *argv],
            timeout=min(timeout, 45.0),
        )
        result = self._decode_guest_result(raw)

        pid = result.get("pid")
        if pid is not None and not result.get("exited"):
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                time.sleep(0.5)
                status_raw = self._qm(
                    target,
                    ["guest", "exec-status", str(target.vmid), str(pid)],
                    timeout=15.0,
                )
                status = self._decode_guest_result(status_raw)
                if status.get("exited"):
                    result = status
                    break
            else:
                raise GuestExecutionError(
                    f"Guest command timed out after {timeout:.0f}s (pid {pid})"
                )

        if result.get("exitcode", 0) != 0:
            raise GuestExecutionError(
                (
                    result.get("err-data")
                    or result.get("out-data")
                    or "guest command failed"
                ).strip()
            )
        return result

    def status(self) -> dict:
        target = self.resolve()
        return {
            "role": target.role,
            "host": target.host,
            "vmid": target.vmid,
            "name": target.name,
            "local": target.local,
            "transport": "restricted_ssh_bridge"
            if self.bridge_host
            else "direct_proxmox",
        }
