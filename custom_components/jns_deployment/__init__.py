from __future__ import annotations

from pathlib import Path
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .const import (
    DOMAIN,
    DEFAULT_INBOX,
    DEFAULT_STAGING,
    DEFAULT_BACKUPS,
)
from .deployment import DeploymentManager, DeploymentError

SERVICE_INSTALL = "install_package"
SERVICE_VALIDATE = "validate_package"
SERVICE_ROLLBACK = "rollback_transaction"

PACKAGE_SCHEMA = vol.Schema(
    {
        vol.Required("package"): cv.string,
        vol.Optional("dry_run", default=False): cv.boolean,
    }
)

ROLLBACK_SCHEMA = vol.Schema(
    {
        vol.Required("transaction_id"): cv.string,
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    manager = DeploymentManager(
        config_root=Path(hass.config.path()),
        inbox_rel=DEFAULT_INBOX,
        staging_rel=DEFAULT_STAGING,
        backups_rel=DEFAULT_BACKUPS,
    )
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = manager

    async def handle_validate(call: ServiceCall):
        result = await hass.async_add_executor_job(
            manager.validate_package, call.data["package"]
        )
        hass.bus.async_fire(f"{DOMAIN}_validation_result", result)

    async def handle_install(call: ServiceCall):
        package = call.data["package"]
        dry_run = call.data.get("dry_run", False)
        try:
            result = await hass.async_add_executor_job(
                manager.install_package, package, dry_run
            )
        except DeploymentError as exc:
            hass.bus.async_fire(
                f"{DOMAIN}_deployment_failed",
                {"package": package, "error": str(exc)},
            )
            raise
        hass.bus.async_fire(f"{DOMAIN}_deployment_result", result)

    async def handle_rollback(call: ServiceCall):
        result = await hass.async_add_executor_job(
            manager.rollback_transaction, call.data["transaction_id"]
        )
        hass.bus.async_fire(f"{DOMAIN}_rollback_result", result)

    hass.services.async_register(
        DOMAIN, SERVICE_VALIDATE, handle_validate, schema=PACKAGE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_INSTALL, handle_install, schema=PACKAGE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_ROLLBACK, handle_rollback, schema=ROLLBACK_SCHEMA
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    if not hass.data.get(DOMAIN):
        for service in (SERVICE_VALIDATE, SERVICE_INSTALL, SERVICE_ROLLBACK):
            hass.services.async_remove(DOMAIN, service)
    return True
