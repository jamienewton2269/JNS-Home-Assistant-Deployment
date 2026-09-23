#!/usr/bin/env python3
"""JNS IoT Gateway core CLI.

Efficiency-first control plane for profile-driven gateway nodes. The core is
normally invoked as a oneshot command or systemd timer, not kept resident.
Only the selected protocol module is expected to run continuously.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import socket
import ssl
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from typing import Any

VERSION = "0.1.0"
DEFAULT_CONFIG = Path("/etc/jns-iot-gateway/gateway.json")
DEFAULT_STATE = Path("/var/lib/jns-iot-gateway/state.json")
DEFAULT_HEALTH = Path("/var/lib/jns-iot-gateway/health.json")
DEFAULT_SPOOL = Path("/var/lib/jns-iot-gateway/syslog-spool.jsonl")
DEFAULT_PROFILE_DIR = Path("/usr/lib/jns-iot-gateway/profiles")
SER2NET_CONFIG = Path("/etc/jns-iot-gateway/ser2net-zigbee.yaml")
ZIGBEE_SERVICE = "jns-iot-zigbee-serial.service"

SEVERITY = {
    "emerg": 0, "alert": 1, "crit": 2, "err": 3,
    "warning": 4, "notice": 5, "info": 6, "debug": 7,
}
FACILITY = {
    "local0": 16, "local1": 17, "local2": 18, "local3": 19,
    "local4": 20, "local5": 21, "local6": 22, "local7": 23,
}
IMPLEMENTED_PROFILES = {"zigbee_serial", "maintenance", "disabled"}


class GatewayError(RuntimeError):
    pass


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".jns-", dir=str(path.parent))
    tmp = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def _atomic_text(path: Path, value: str, mode: int = 0o640) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".jns-", dir=str(path.parent))
    tmp = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def load_json(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except FileNotFoundError as exc:
        raise GatewayError(f"Configuration not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise GatewayError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise GatewayError(f"Expected an object in {path}")
    return data


def profile_name(config: dict[str, Any]) -> str:
    value = str(config.get("profile", {}).get("active", "")).strip().lower()
    if not value:
        raise GatewayError("profile.active is required")
    if not all(ch.isalnum() or ch in "_-" for ch in value):
        raise GatewayError("profile.active contains invalid characters")
    return value


def load_profile(name: str, profile_dir: Path = DEFAULT_PROFILE_DIR) -> dict[str, Any]:
    return load_json(profile_dir / f"{name}.json")


def validate_config(config: dict[str, Any], profile: dict[str, Any]) -> None:
    selected = profile_name(config)
    if profile.get("id") != selected:
        raise GatewayError("profile manifest id does not match profile.active")
    if selected not in IMPLEMENTED_PROFILES:
        raise GatewayError(
            f"Profile {selected!r} is reserved for a future module and is not implemented in v{VERSION}."
        )
    if selected == "zigbee_serial":
        radio = config.get("hardware", {}).get("radio_1", {})
        device = str(radio.get("device", "")).strip()
        if not device.startswith("/dev/serial/by-id/"):
            raise GatewayError(
                "zigbee_serial requires hardware.radio_1.device to use a stable /dev/serial/by-id/ path"
            )
        port = int(config.get("zigbee_serial", {}).get("listen_port", 20108))
        if not 1 <= port <= 65535:
            raise GatewayError("zigbee_serial.listen_port must be between 1 and 65535")
        baud = int(config.get("zigbee_serial", {}).get("baudrate", 115200))
        if baud <= 0:
            raise GatewayError("zigbee_serial.baudrate must be positive")
    syslog_cfg = config.get("logging", {}).get("syslog", {})
    if syslog_cfg.get("enabled"):
        if not str(syslog_cfg.get("server", "")).strip():
            raise GatewayError("logging.syslog.server is required when syslog is enabled")
        transport = str(syslog_cfg.get("transport", "udp")).lower()
        if transport not in {"udp", "tcp", "tls"}:
            raise GatewayError("logging.syslog.transport must be udp, tcp or tls")
        facility = str(syslog_cfg.get("facility", "local5")).lower()
        if facility not in FACILITY:
            raise GatewayError(f"Unsupported syslog facility: {facility}")


def render_ser2net(config: dict[str, Any]) -> str:
    radio = config["hardware"]["radio_1"]
    zigbee = config.get("zigbee_serial", {})
    device = str(radio["device"])
    baud = int(zigbee.get("baudrate", 115200))
    port = int(zigbee.get("listen_port", 20108))
    bind = str(zigbee.get("bind", "0.0.0.0")).strip() or "0.0.0.0"
    accepter = f"tcp,{bind},{port}" if bind not in {"0.0.0.0", "::"} else f"tcp,{port}"
    return (
        "%YAML 1.1\n---\n"
        "connection: &jns_zigbee\n"
        f"  accepter: {accepter}\n"
        "  enable: on\n"
        f"  connector: serialdev,{device},{baud}n81,local\n"
        "  options:\n"
        "    max-connections: 1\n"
        "    kickolduser: false\n"
    )


def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, capture_output=True, check=check)


def systemctl(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return run(["systemctl", *args], check=check)


def service_active(name: str) -> bool:
    return systemctl("is-active", "--quiet", name, check=False).returncode == 0


def service_exists(name: str) -> bool:
    return systemctl("cat", name, check=False).returncode == 0


def _escape_sd(value: Any) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"').replace("]", "\\]")


def build_rfc5424(config: dict[str, Any], event: str, severity: str,
                  fields: dict[str, Any], message: str) -> str:
    syslog_cfg = config.get("logging", {}).get("syslog", {})
    facility = FACILITY.get(str(syslog_cfg.get("facility", "local5")).lower(), 21)
    sev = SEVERITY.get(severity.lower(), 6)
    pri = facility * 8 + sev
    timestamp = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    hostname = socket.gethostname() or "-"
    app = str(syslog_cfg.get("app_name", "jns-iot-gateway"))[:48] or "jns-iot-gateway"
    node_id = str(config.get("node", {}).get("id", hostname))
    profile = str(config.get("profile", {}).get("active", "unknown"))
    structured = {"node": node_id, "profile": profile, **fields}
    sd_params = " ".join(f'{k}="{_escape_sd(v)}"' for k, v in sorted(structured.items()))
    sd = f"[jns@32473 {sd_params}]" if sd_params else "-"
    clean_event = "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in event)[:32] or "JNS_EVENT"
    msg = message.replace("\n", " ").strip() if message else event
    return f"<{pri}>1 {timestamp} {hostname} {app} - {clean_event} {sd} {msg}"


def _send_syslog(config: dict[str, Any], message: str) -> None:
    cfg = config.get("logging", {}).get("syslog", {})
    host = str(cfg.get("server", "")).strip()
    transport = str(cfg.get("transport", "udp")).lower()
    default_port = 6514 if transport == "tls" else 514
    port = int(cfg.get("port", default_port))
    timeout = float(cfg.get("timeout_seconds", 2.0))
    payload = message.encode("utf-8", errors="replace")
    if transport == "udp":
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(timeout)
            sock.sendto(payload, (host, port))
        return
    framed = f"{len(payload)} ".encode("ascii") + payload
    raw = socket.create_connection((host, port), timeout=timeout)
    try:
        if transport == "tls":
            context = ssl.create_default_context(cafile=cfg.get("ca_file") or None)
            if cfg.get("verify_certificate", True) is False:
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
            with context.wrap_socket(raw, server_hostname=host if context.check_hostname else None) as sock:
                sock.sendall(framed)
        else:
            with raw:
                raw.sendall(framed)
    finally:
        try:
            raw.close()
        except OSError:
            pass


def _spool_append(config: dict[str, Any], message: str, spool: Path = DEFAULT_SPOOL) -> None:
    cfg = config.get("logging", {}).get("syslog", {})
    max_events = max(1, min(int(cfg.get("spool_max_events", 256)), 4096))
    spool.parent.mkdir(parents=True, exist_ok=True)
    existing = spool.read_text(encoding="utf-8", errors="replace").splitlines() if spool.exists() else []
    existing.append(json.dumps({"message": message}, separators=(",", ":")))
    existing = existing[-max_events:]
    _atomic_text(spool, "\n".join(existing) + "\n", 0o600)


def emit_event(config: dict[str, Any], event: str, severity: str = "info",
               fields: dict[str, Any] | None = None, message: str = "",
               spool: Path = DEFAULT_SPOOL) -> bool:
    cfg = config.get("logging", {}).get("syslog", {})
    if not cfg.get("enabled"):
        return True
    wire = build_rfc5424(config, event, severity, fields or {}, message)
    try:
        _send_syslog(config, wire)
        return True
    except (OSError, ssl.SSLError, ValueError):
        _spool_append(config, wire, spool)
        return False


def flush_spool(config: dict[str, Any], spool: Path = DEFAULT_SPOOL) -> tuple[int, int]:
    if not spool.exists() or not config.get("logging", {}).get("syslog", {}).get("enabled"):
        return 0, 0
    lines = spool.read_text(encoding="utf-8", errors="replace").splitlines()
    retained: list[str] = []
    sent = 0
    for index, line in enumerate(lines):
        try:
            _send_syslog(config, str(json.loads(line)["message"]))
            sent += 1
        except Exception:
            retained.extend(lines[index:])
            break
    if retained:
        _atomic_text(spool, "\n".join(retained) + "\n", 0o600)
    else:
        spool.unlink(missing_ok=True)
    return sent, len(retained)


def apply_profile(config: dict[str, Any], profile: dict[str, Any],
                  dry_run: bool = False) -> dict[str, Any]:
    validate_config(config, profile)
    selected = profile_name(config)
    actions: list[str] = []
    if selected == "zigbee_serial":
        radio_path = Path(config["hardware"]["radio_1"]["device"])
        if not radio_path.exists():
            raise GatewayError(f"Configured coordinator is not present: {radio_path}")
        actions.extend([f"write {SER2NET_CONFIG}", f"enable/start {ZIGBEE_SERVICE}"])
        if not dry_run:
            _atomic_text(SER2NET_CONFIG, render_ser2net(config), 0o640)
            systemctl("daemon-reload")
            systemctl("enable", "--now", ZIGBEE_SERVICE)
    else:
        if service_exists(ZIGBEE_SERVICE):
            actions.append(f"disable/stop {ZIGBEE_SERVICE}")
            if not dry_run:
                systemctl("disable", "--now", ZIGBEE_SERVICE, check=False)
        if not dry_run:
            SER2NET_CONFIG.unlink(missing_ok=True)

    state = {
        "version": VERSION,
        "node_id": config.get("node", {}).get("id"),
        "profile": selected,
        "configuration_sha256": hashlib.sha256(
            json.dumps(config, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "applied_utc": datetime.now(timezone.utc).isoformat(),
        "actions": actions,
    }
    if not dry_run:
        _atomic_json(DEFAULT_STATE, state)
        emit_event(config, "PROFILE_APPLY_COMPLETE",
                   fields={"config_sha256": state["configuration_sha256"]})
    return state


def health_snapshot(config: dict[str, Any]) -> dict[str, Any]:
    selected = profile_name(config)
    health: dict[str, Any] = {
        "node_id": config.get("node", {}).get("id"),
        "profile": selected,
        "version": VERSION,
        "checked_utc": datetime.now(timezone.utc).isoformat(),
        "healthy": True,
    }
    if selected == "zigbee_serial":
        device = Path(config["hardware"]["radio_1"]["device"])
        health["radio_present"] = device.exists()
        health["service_active"] = service_active(ZIGBEE_SERVICE)
        health["healthy"] = bool(health["radio_present"] and health["service_active"])
    return health


def record_health(config: dict[str, Any], health: dict[str, Any],
                  path: Path = DEFAULT_HEALTH) -> bool:
    previous: dict[str, Any] = {}
    if path.exists():
        try:
            previous = load_json(path)
        except GatewayError:
            previous = {}
    changed = any(previous.get(k) != health.get(k)
                  for k in ("healthy", "profile", "radio_present", "service_active"))
    _atomic_json(path, health)
    if changed:
        emit_event(
            config,
            "HEALTH_RECOVERED" if health.get("healthy") else "HEALTH_DEGRADED",
            severity="info" if health.get("healthy") else "warning",
            fields={k: v for k, v in health.items() if k != "checked_utc"},
        )
    return changed


def cmd_validate(args: argparse.Namespace) -> int:
    config = load_json(args.config)
    profile = load_profile(profile_name(config), args.profile_dir)
    validate_config(config, profile)
    print("VALID")
    return 0


def cmd_apply(args: argparse.Namespace) -> int:
    config = load_json(args.config)
    profile = load_profile(profile_name(config), args.profile_dir)
    print(json.dumps(apply_profile(config, profile, args.dry_run), indent=2, sort_keys=True))
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    config = load_json(args.config)
    profile = load_profile(profile_name(config), args.profile_dir)
    validate_config(config, profile)
    result = health_snapshot(config)
    if DEFAULT_STATE.exists():
        try:
            result["deployment"] = load_json(DEFAULT_STATE)
        except GatewayError:
            pass
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("healthy") else 2


def cmd_health(args: argparse.Namespace) -> int:
    config = load_json(args.config)
    profile = load_profile(profile_name(config), args.profile_dir)
    validate_config(config, profile)
    flush_spool(config)
    result = health_snapshot(config)
    record_health(config, result)
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("healthy") else 2


def cmd_emit(args: argparse.Namespace) -> int:
    config = load_json(args.config)
    fields: dict[str, Any] = {}
    for item in args.field:
        if "=" not in item:
            raise GatewayError(f"Invalid --field {item!r}; expected key=value")
        key, value = item.split("=", 1)
        fields[key] = value
    delivered = emit_event(config, args.event, args.severity, fields, args.message)
    print("sent" if delivered else "spooled")
    return 0


def cmd_flush(args: argparse.Namespace) -> int:
    config = load_json(args.config)
    sent, retained = flush_spool(config)
    print(json.dumps({"sent": sent, "retained": retained}))
    return 0 if retained == 0 else 1


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="jns-gateway", description="JNS IoT Gateway profile manager")
    p.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    p.add_argument("--profile-dir", type=Path, default=DEFAULT_PROFILE_DIR)
    p.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    sub = p.add_subparsers(dest="command", required=True)

    v = sub.add_parser("validate")
    v.set_defaults(func=cmd_validate)

    a = sub.add_parser("apply")
    a.add_argument("--dry-run", action="store_true")
    a.set_defaults(func=cmd_apply)

    s = sub.add_parser("status")
    s.set_defaults(func=cmd_status)

    h = sub.add_parser("health")
    h.set_defaults(func=cmd_health)

    e = sub.add_parser("emit")
    e.add_argument("event")
    e.add_argument("--severity", choices=sorted(SEVERITY), default="info")
    e.add_argument("--field", action="append", default=[])
    e.add_argument("--message", default="")
    e.set_defaults(func=cmd_emit)

    f = sub.add_parser("flush-syslog")
    f.set_defaults(func=cmd_flush)
    return p


def main() -> int:
    try:
        args = parser().parse_args()
        return int(args.func(args))
    except GatewayError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except subprocess.CalledProcessError as exc:
        command = " ".join(shlex.quote(x) for x in exc.cmd)
        detail = (exc.stderr or exc.stdout or "").strip()
        print(f"ERROR: command failed: {command}: {detail}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
