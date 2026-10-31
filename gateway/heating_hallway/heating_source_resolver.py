"""Read-only, offline/VM905-local device-identity resolver for candidate release.

Never search by advertised friendly name alone: source is the exact supplied
HA hallway device ID plus the Zigbee IEEE of the living-room sensor.
Run in a PRIVATE operator context. Never publish the raw device registry.
"""
from __future__ import annotations
from pathlib import Path
import json

HALLWAY_DEVICE_ID = "3fc0d19af1ae3fad19d67ae05b4ccb0f"
FIREPLACE_IEEE = "0xa4c138818d33ffff"
BATHROOM_TEMP = "sensor.0xa4c1382471d2ed23_temperature"
HONEYWELL_INDOOR = "sensor.thermostat_thermostat_indoor_temperature"
HONEYWELL_OUTDOOR = "sensor.thermostat_thermostat_outdoor_temperature"
HONEYWELL_CLIMATE = "climate.thermostat_thermostat"
PLANT_CANDIDATES = (
    "sensor.ha900_temphumid2_temperature",
    "sensor.ha900_moistures1_temperature",
    "sensor.ha900_moisture2_temperature",
    "sensor.ha900_moisture3_temperature",
)

class ResolutionError(RuntimeError):
    pass


def _records(data, section):
    result = data.get("data", {}).get(section)
    if not isinstance(result, list):
        raise ResolutionError(f"{section} unavailable")
    return result


def _temperatures_for_device(entities, device_id):
    choices = []
    for e in entities:
        if e.get("device_id") != device_id or e.get("disabled_by"):
            continue
        eid = e.get("entity_id", "")
        if not eid.startswith("sensor."):
            continue
        kind = e.get("device_class") or e.get("original_device_class")
        if kind == "temperature" or eid.endswith("_temperature"):
            choices.append(eid)
    return sorted(set(choices))


def resolve(devices_doc, entities_doc):
    devices = _records(devices_doc, "devices")
    entities = _records(entities_doc, "entities")
    if len([d for d in devices if d.get("id") == HALLWAY_DEVICE_ID]) != 1:
        raise ResolutionError("Hallway device ID not uniquely present on VM905")
    hall = _temperatures_for_device(entities, HALLWAY_DEVICE_ID)
    if len(hall) != 1:
        raise ResolutionError("Hallway must resolve to exactly one enabled temperature")
    fireplace_device_ids = []
    for d in devices:
        tokens = [str(x).lower() for entry in d.get("identifiers", []) for x in entry]
        # Zigbee2MQTT can encode the IEEE in an MQTT unique identifier.
        if any(FIREPLACE_IEEE in x for x in tokens):
            fireplace_device_ids.append(d["id"])
    if not fireplace_device_ids:
        for e in entities:
            if FIREPLACE_IEEE in str(e.get("unique_id", "")).lower() and e.get("device_id"):
                fireplace_device_ids.append(e["device_id"])
    fireplace_device_ids = sorted(set(fireplace_device_ids))
    if len(fireplace_device_ids) != 1 or fireplace_device_ids[0] == HALLWAY_DEVICE_ID:
        raise ResolutionError("Fireplace Zigbee identity not uniquely proven")
    fire = _temperatures_for_device(entities, fireplace_device_ids[0])
    if len(fire) != 1:
        raise ResolutionError("Fireplace must resolve to exactly one enabled temperature")
    enabled_ids = {e.get("entity_id") for e in entities if not e.get("disabled_by")}
    required = {BATHROOM_TEMP, HONEYWELL_INDOOR, HONEYWELL_OUTDOOR, HONEYWELL_CLIMATE}
    if not required.issubset(enabled_ids):
        raise ResolutionError("Reference thermometer/Honeywell entity not found or disabled")
    plant = [n for n in PLANT_CANDIDATES if n in enabled_ids]
    # Device registry proves entities, not live MQTT freshness. A later live
    # authenticated /api/states inspection MUST verify current report times.
    return {"hallway": hall[0], "fireplace": fire[0],
            "bathroom": BATHROOM_TEMP, "honeywell_indoor": HONEYWELL_INDOOR,
            "honeywell_outdoor": HONEYWELL_OUTDOOR,
            "honeywell_climate": HONEYWELL_CLIMATE, "plant": plant,
            "missing_plant": sorted(set(PLANT_CANDIDATES) - set(plant))}


def resolve_private_config(root="/config"):
    root = Path(root)
    devices = json.loads((root/".storage/core.device_registry").read_text())
    entities = json.loads((root/".storage/core.entity_registry").read_text())
    return resolve(devices, entities)
