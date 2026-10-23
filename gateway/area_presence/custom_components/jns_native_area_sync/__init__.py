"""Native JNS MQTT Area Synchroniser (add-only, conflict-aware).

HA-General VM905 owns catalogue jns/site/areas/catalogue.
Enable only on receiver HA nodes after native MQTT has been configured.
Never changes existing area names, deletes areas, or edits device/entity assignments.
"""
import json
import logging
from datetime import datetime, timezone

import voluptuous as vol

from homeassistant.components import mqtt
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import config_validation as cv
from homeassistant.util import slugify

DOMAIN = "jns_native_area_sync"
CATALOGUE_TOPIC = "jns/site/areas/catalogue"
REPORT_TOPIC_PREFIX = "jns/site/areas/sync"
_LOGGER = logging.getLogger(__name__)
CONFIG_SCHEMA = vol.Schema(
    {DOMAIN: vol.Schema({
        vol.Optional("apply", default=False): cv.boolean,
        vol.Optional("node", default="ha-primary"): cv.string,
    })},
    extra=vol.ALLOW_EXTRA,
)

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Subscribe to retained catalogue; native HA registry handles all writes."""
    opts = config[DOMAIN]
    node = opts["node"]
    apply = opts["apply"]
    if not node or not all(c.isalnum() or c in "_-" for c in node):
        _LOGGER.error("Invalid node identifier")
        return False

    # MQTT is a manifest dependency; await active client before subscribe.
    if not await mqtt.async_wait_for_mqtt_client(hass):
        _LOGGER.error("Native MQTT client unavailable; area sync not started")
        return False

    @callback
    def parse_catalogue(payload: str):
        data = json.loads(payload)
        if not isinstance(data, dict) or data.get("schema") != "jns.area-catalogue.v1":
            raise ValueError("Unsupported schema")
        if data.get("source") != "ha-general":
            raise ValueError("Wrong authoritative source")
        entries = data.get("areas")
        if not isinstance(entries, list) or len(entries) > 100:
            raise ValueError("Invalid area count")
        ids, names, clean = set(), set(), []
        for obj in entries:
            if not isinstance(obj, dict):
                raise ValueError("Invalid area entry")
            aid, name = obj.get("id"), obj.get("name")
            if not isinstance(aid, str) or not isinstance(name, str):
                raise ValueError("Invalid area entry types")
            if not 1 <= len(aid) <= 64 or not 1 <= len(name) <= 120:
                raise ValueError("Invalid area lengths")
            if aid in ids or name.casefold() in names:
                raise ValueError("Duplicate area id/name")
            ids.add(aid)
            names.add(name.casefold())
            clean.append((aid, name))
        return clean

    async def on_catalogue(message):
        """Reconcile only known, validated, authoritative catalogue."""
        try:
            entries = parse_catalogue(message.payload)
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            _LOGGER.warning("Rejected JNS area catalogue: %s", type(exc).__name__)
            return
        registry = ar.async_get(hass)
        created, identical, conflicts, missing = [], [], [], []
        for wanted_id, wanted_name in entries:
            current = registry.async_get_area(wanted_id)
            if current:
                if current.name.casefold() == wanted_name.casefold():
                    identical.append(wanted_id)
                else:
                    conflicts.append(wanted_id + ":name-conflict")
                continue
            by_name = registry.async_get_area_by_name(wanted_name)
            if by_name:
                conflicts.append(wanted_id + ":name-owned-by-another-id")
                continue
            if slugify(wanted_name) != wanted_id:
                conflicts.append(wanted_id + ":would-change-id")
                continue
            if not apply:
                missing.append(wanted_id)
                continue
            try:
                entry = registry.async_create(name=wanted_name)
                if entry.id != wanted_id:
                    # Never automatically delete or rename an area. Report unexpected ID.
                    conflicts.append(wanted_id + ":created-id-different")
                else:
                    created.append(wanted_id)
            except (ValueError, KeyError):
                conflicts.append(wanted_id + ":create-error")
        report = {
            "schema": "jns.area-sync-report.v1",
            "node": node,
            "source": "ha-general",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "mode": "apply" if apply else "dry_run",
            "created": created,
            "missing": missing,
            "already_present": identical,
            "conflicts": conflicts,
        }
        hass.data[DOMAIN]["last_report"] = report
        # Use same native MQTT integration; do not open another broker connection.
        await mqtt.async_publish(hass, REPORT_TOPIC_PREFIX + "/" + node,
                                 json.dumps(report, separators=(",", ":")),
                                 qos=0, retain=True)
        if conflicts:
            _LOGGER.warning("JNS area reconciliation has %d conflicts; no rename/delete performed", len(conflicts))
        else:
            _LOGGER.info("JNS areas %s: %d existing, %d created, %d missing",
                         node, len(identical), len(created), len(missing))

    hass.data[DOMAIN] = {"last_report": None}
    unsub = await mqtt.async_subscribe(hass, CATALOGUE_TOPIC, on_catalogue, qos=0)
    hass.bus.async_listen_once("homeassistant_stop", lambda _: unsub())
    return True
