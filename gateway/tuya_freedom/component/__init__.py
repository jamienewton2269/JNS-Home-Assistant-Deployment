"""Read-only, token-free in-process JNS Tuya cloud-to-local observer.

Runs as a normally configured Home Assistant integration and uses hass.states
and native registries. No HA admin token, cloud account, local device probe,
device command, config flow, entity rename, or external network request.
Detailed identity and state reports stay on the user's own HA instance.
"""
from __future__ import annotations

import asyncio
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path

import voluptuous as vol

from homeassistant.const import EVENT_HOMEASSISTANT_STARTED, EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.event import async_track_time_interval

DOMAIN = "jns_tuya_freedom"
CONFIG_SCHEMA = vol.Schema({vol.Optional(DOMAIN): vol.Schema({})}, extra=vol.ALLOW_EXTRA)
INTERVAL = timedelta(minutes=5)
TARGET = Path("/config/.jns_tuya_freedom/latest-live.json")


def _atomic_write(payload: dict) -> None:
    """Write a private 0600 report without logging identities or credentials."""
    directory = TARGET.parent
    if directory.is_symlink():
        raise OSError("Private directory is a symlink")
    directory.mkdir(mode=0o700, exist_ok=True)
    os.chmod(directory, 0o700)
    if TARGET.is_symlink():
        raise OSError("Output file is a symlink")
    # A fixed filename with an exclusive per-process temporary name avoids
    # predictable file races and never modifies config entries or HA registries.
    import secrets
    temp = directory / ("._latest-live-" + secrets.token_hex(8))
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(str(temp), flags, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, sort_keys=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, TARGET)
        os.chmod(TARGET, 0o600)
    finally:
        if temp.exists():
            temp.unlink()


def _native_cloud_ids(device) -> set[str]:
    values: set[str] = set()
    for domain, value in getattr(device, "identifiers", ()):
        if str(domain).lower() == "tuya" and len(str(value).strip()) >= 12:
            values.add(str(value).strip().lower())
    return values


def _snapshot(hass: HomeAssistant) -> dict:
    config_by_id = {entry.entry_id: entry for entry in hass.config_entries.async_entries()}
    local_entries = [
        entry for entry in config_by_id.values() if entry.domain == "tuya_local"
    ]
    cloud_entry_ids = {
        entry.entry_id for entry in config_by_id.values() if entry.domain == "tuya"
    }

    device_registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)
    by_device = defaultdict(list)
    for entity in entity_registry.entities.values():
        if entity.device_id:
            by_device[entity.device_id].append(entity)

    # Unlike registry records, Tuya identifiers refer to physical devices.
    cloud_physical = defaultdict(list)
    for device in device_registry.devices.values():
        if not cloud_entry_ids.intersection(device.config_entries):
            continue
        identifiers = _native_cloud_ids(device)
        if len(identifiers) == 1:
            cloud_physical[next(iter(identifiers))].append(device)

    local_by_id = defaultdict(list)
    for entry in local_entries:
        native_id = entry.data.get("device_id")
        if isinstance(native_id, str) and len(native_id.strip()) >= 12:
            local_by_id[native_id.strip().lower()].append(entry)

    counts = Counter()
    rows = []
    for native_id, cloud_registrations in sorted(cloud_physical.items()):
        matching_local = local_by_id.get(native_id, [])
        local_entry_ids = {entry.entry_id for entry in matching_local}
        local_device_records = [
            device for device in device_registry.devices.values()
            if local_entry_ids.intersection(device.config_entries)
        ]
        states_by_id = {}
        enabled_entity_count = 0
        loaded = 0
        available = 0
        for device in local_device_records:
            for entity in by_device.get(device.id, []):
                if entity.platform != "tuya_local" or entity.disabled_by is not None:
                    continue
                enabled_entity_count += 1
                value = hass.states.get(entity.entity_id)
                state = value.state if value is not None else "not_loaded"
                if value is not None:
                    loaded += 1
                if state not in ("not_loaded", "unavailable", "unknown"):
                    available += 1
                states_by_id[entity.entity_id] = state
        counts["unique_physical_cloud_devices"] += 1
        if matching_local:
            counts["with_existing_local_entry"] += 1
            counts["local_enabled_entities"] += enabled_entity_count
            counts["local_loaded_entities"] += loaded
            counts["local_available_entities"] += available
            counts["local_devices_with_available_entity"] += int(available > 0)
            counts["local_devices_all_enabled_entities_available"] += int(
                enabled_entity_count > 0 and enabled_entity_count == available
            )
        else:
            counts["still_needing_local_onboarding"] += 1
        names = [
            d.name_by_user or d.name for d in cloud_registrations
            if d.name_by_user or d.name
        ]
        rows.append({
            "native_device_id": native_id,
            "name": names[0] if names else "",
            "local_configured": bool(matching_local),
            "local_config_entries": len(matching_local),
            "local_key_present": any(bool(e.data.get("local_key")) for e in matching_local),
            "enabled_local_entities": enabled_entity_count,
            "loaded_local_entities": loaded,
            "available_local_entities": available,
            "local_entity_states": states_by_id,
            "off_wan_proof": False,
            "ready_to_cutover": False,
        })

    return {
        "schema": 1,
        "observer_version": "0.1.0",
        "mode": "in_process_read_only",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "security_note": "PRIVATE: no keys or tokens stored. State availability is NOT a WAN-offline proof.",
        "aggregate": dict(counts),
        "physical_devices": rows,
    }


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Use existing Home Assistant in-memory state; no token or REST calls."""
    if DOMAIN not in config:
        return True

    lock = asyncio.Lock()

    async def observe() -> None:
        if lock.locked():
            return
        async with lock:
            payload = _snapshot(hass)
            try:
                await hass.async_add_executor_job(_atomic_write, payload)
            except OSError:
                # Never log report data, entity names, IDs, hosts, or exceptions
                # that may reveal paths. A failure simply leaves last snapshot.
                return

    def trigger() -> None:
        hass.async_create_background_task(observe(), "JNS Tuya Freedom observer")

    @callback
    def on_start(_event) -> None:
        trigger()

    @callback
    def on_timer(_now) -> None:
        trigger()

    if hass.is_running:
        trigger()
    else:
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, on_start)

    cancel = async_track_time_interval(hass, on_timer, INTERVAL)

    @callback
    def on_stop(_event) -> None:
        cancel()

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, on_stop)
    return True
