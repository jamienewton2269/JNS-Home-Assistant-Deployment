from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, VERSION
from .deployment import DeploymentManager


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict[str, Any]:
    manager = hass.data.get(DOMAIN, {}).get("manager")
    if not isinstance(manager, DeploymentManager):
        return {
            "version": VERSION,
            "loaded": False,
        }

    status = await hass.async_add_executor_job(
        manager.get_status,
        VERSION,
    )
    transactions = await hass.async_add_executor_job(
        manager.list_transactions,
        20,
    )

    return {
        "version": VERSION,
        "loaded": True,
        "status": status,
        "transactions": transactions,
    }
