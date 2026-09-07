from __future__ import annotations

from pathlib import Path
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import check_config as conf_util
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import (
    DEFAULT_BACKUPS,
    DEFAULT_INBOX,
    DEFAULT_PLATFORM_UPDATES,
    DEFAULT_STAGING,
    DEFAULT_STATE,
    DOMAIN,
    VERSION,
)
from .deployment import DeploymentError, DeploymentManager

SERVICE_STATUS = "status"
SERVICE_LIST_INBOX = "list_inbox_packages"
SERVICE_PLAN = "plan_package"
SERVICE_VALIDATE = "validate_package"
SERVICE_INSTALL = "install_package"
SERVICE_ROLLBACK = "rollback_transaction"
SERVICE_RECOVER = "recover_interrupted_transaction"
SERVICE_LIST_TRANSACTIONS = "list_transactions"
SERVICE_GET_TRANSACTION = "get_transaction"
SERVICE_LIST_INSTALLED = "list_installed_packages"

SERVICE_VALIDATE_PLATFORM = "validate_platform_update"
SERVICE_INSTALL_PLATFORM = "install_platform_update"
SERVICE_ROLLBACK_PLATFORM = "rollback_platform_update"

PACKAGE_SCHEMA = vol.Schema(
    {
        vol.Required("package"): cv.string,
    }
)

INSTALL_SCHEMA = vol.Schema(
    {
        vol.Required("package"): cv.string,
        vol.Optional("dry_run", default=False): cv.boolean,
        vol.Optional("check_config", default=True): cv.boolean,
    }
)

ROLLBACK_SCHEMA = vol.Schema(
    {
        vol.Required("transaction_id"): cv.string,
        vol.Optional("force", default=False): cv.boolean,
        vol.Optional("check_config", default=True): cv.boolean,
    }
)

TRANSACTION_SCHEMA = vol.Schema(
    {
        vol.Required("transaction_id"): cv.string,
    }
)

LIST_SCHEMA = vol.Schema(
    {
        vol.Optional("limit", default=50): vol.All(
            vol.Coerce(int),
            vol.Range(min=1, max=100),
        ),
    }
)

PLATFORM_SCHEMA = vol.Schema(
    {
        vol.Required("package"): cv.string,
        vol.Required("expected_sha256"): cv.string,
        vol.Optional("dry_run", default=False): cv.boolean,
    }
)

PLATFORM_ROLLBACK_SCHEMA = vol.Schema(
    {
        vol.Required("transaction_id"): cv.string,
    }
)


def _get_manager(hass: HomeAssistant) -> DeploymentManager:
    manager = hass.data.get(DOMAIN, {}).get("manager")
    if not isinstance(manager, DeploymentManager):
        raise ServiceValidationError(
            "JNS Deployment Platform is not loaded."
        )
    return manager


async def _executor_call(
    hass: HomeAssistant,
    method: Any,
    *args: Any,
) -> dict[str, Any]:
    try:
        return await hass.async_add_executor_job(method, *args)
    except DeploymentError as exc:
        raise ServiceValidationError(str(exc)) from exc
    except OSError as exc:
        raise HomeAssistantError(
            f"JNS filesystem operation failed: {exc}"
        ) from exc


async def _config_check_or_rollback(
    hass: HomeAssistant,
    manager: DeploymentManager,
    transaction_id: str,
) -> dict[str, Any]:
    """Run HA's own configuration validation; rollback on any failure."""
    try:
        errors = await conf_util.async_check_ha_config_file(hass)
    except Exception as exc:
        await _executor_call(
            hass,
            manager.rollback_transaction,
            transaction_id,
            False,
        )
        raise HomeAssistantError(
            "Home Assistant configuration validation raised an unexpected "
            f"error. JNS rolled back transaction {transaction_id}: {exc}"
        ) from exc

    if errors:
        await _executor_call(
            hass,
            manager.rollback_transaction,
            transaction_id,
            False,
        )
        raise ServiceValidationError(
            "Home Assistant configuration validation failed. "
            f"JNS rolled back transaction {transaction_id}: {errors}"
        )

    return {
        "status": "passed",
        "errors": None,
    }


async def async_setup(
    hass: HomeAssistant,
    config: ConfigType,
) -> bool:
    async def handle_status(call: ServiceCall) -> ServiceResponse:
        manager = _get_manager(hass)
        return await _executor_call(
            hass,
            manager.get_status,
            VERSION,
        )

    async def handle_list_inbox(
        call: ServiceCall,
    ) -> ServiceResponse:
        manager = _get_manager(hass)
        return await _executor_call(
            hass,
            manager.list_inbox_packages,
        )

    async def handle_plan(call: ServiceCall) -> ServiceResponse:
        manager = _get_manager(hass)
        return await _executor_call(
            hass,
            manager.plan_package,
            call.data["package"],
        )

    async def handle_validate(
        call: ServiceCall,
    ) -> ServiceResponse:
        manager = _get_manager(hass)
        result = await _executor_call(
            hass,
            manager.validate_package,
            call.data["package"],
        )
        hass.bus.async_fire(f"{DOMAIN}_validation_result", result)
        return result

    async def handle_install(
        call: ServiceCall,
    ) -> ServiceResponse:
        manager = _get_manager(hass)
        dry_run = call.data.get("dry_run", False)
        result = await _executor_call(
            hass,
            manager.install_package,
            call.data["package"],
            dry_run,
        )

        if (
            result.get("installed")
            and call.data.get("check_config", True)
        ):
            config_result = await _config_check_or_rollback(
                hass,
                manager,
                result["transaction_id"],
            )
            result["home_assistant_config_check"] = config_result
        elif result.get("installed"):
            result["home_assistant_config_check"] = {
                "status": "skipped"
            }

        hass.bus.async_fire(f"{DOMAIN}_deployment_result", result)
        return result

    async def handle_rollback(
        call: ServiceCall,
    ) -> ServiceResponse:
        manager = _get_manager(hass)
        result = await _executor_call(
            hass,
            manager.rollback_transaction,
            call.data["transaction_id"],
            call.data.get("force", False),
        )

        if call.data.get("check_config", True):
            errors = await conf_util.async_check_ha_config_file(hass)
            result["home_assistant_config_check"] = {
                "status": "passed" if not errors else "failed",
                "errors": str(errors) if errors else None,
            }

        hass.bus.async_fire(f"{DOMAIN}_rollback_result", result)
        return result

    async def handle_recover(
        call: ServiceCall,
    ) -> ServiceResponse:
        manager = _get_manager(hass)
        result = await _executor_call(
            hass,
            manager.recover_interrupted_transaction,
            call.data["transaction_id"],
        )
        hass.bus.async_fire(f"{DOMAIN}_recovery_result", result)
        return result

    async def handle_list_transactions(
        call: ServiceCall,
    ) -> ServiceResponse:
        manager = _get_manager(hass)
        return await _executor_call(
            hass,
            manager.list_transactions,
            call.data.get("limit", 50),
        )

    async def handle_get_transaction(
        call: ServiceCall,
    ) -> ServiceResponse:
        manager = _get_manager(hass)
        return await _executor_call(
            hass,
            manager.get_transaction,
            call.data["transaction_id"],
        )

    async def handle_list_installed(
        call: ServiceCall,
    ) -> ServiceResponse:
        manager = _get_manager(hass)
        return await _executor_call(
            hass,
            manager.list_installed_packages,
        )

    async def handle_validate_platform(
        call: ServiceCall,
    ) -> ServiceResponse:
        manager = _get_manager(hass)
        return await _executor_call(
            hass,
            manager.validate_platform_update,
            call.data["package"],
            call.data["expected_sha256"],
            VERSION,
        )

    async def handle_install_platform(
        call: ServiceCall,
    ) -> ServiceResponse:
        manager = _get_manager(hass)
        result = await _executor_call(
            hass,
            manager.install_platform_update,
            call.data["package"],
            call.data["expected_sha256"],
            VERSION,
            call.data.get("dry_run", False),
        )
        hass.bus.async_fire(f"{DOMAIN}_platform_update_result", result)
        return result

    async def handle_rollback_platform(
        call: ServiceCall,
    ) -> ServiceResponse:
        manager = _get_manager(hass)
        result = await _executor_call(
            hass,
            manager.rollback_platform_update,
            call.data["transaction_id"],
        )
        hass.bus.async_fire(
            f"{DOMAIN}_platform_rollback_result",
            result,
        )
        return result

    response_services = (
        (SERVICE_STATUS, handle_status, vol.Schema({})),
        (SERVICE_LIST_INBOX, handle_list_inbox, vol.Schema({})),
        (SERVICE_PLAN, handle_plan, PACKAGE_SCHEMA),
        (SERVICE_VALIDATE, handle_validate, PACKAGE_SCHEMA),
        (SERVICE_INSTALL, handle_install, INSTALL_SCHEMA),
        (SERVICE_ROLLBACK, handle_rollback, ROLLBACK_SCHEMA),
        (SERVICE_RECOVER, handle_recover, TRANSACTION_SCHEMA),
        (
            SERVICE_LIST_TRANSACTIONS,
            handle_list_transactions,
            LIST_SCHEMA,
        ),
        (
            SERVICE_GET_TRANSACTION,
            handle_get_transaction,
            TRANSACTION_SCHEMA,
        ),
        (
            SERVICE_LIST_INSTALLED,
            handle_list_installed,
            vol.Schema({}),
        ),
        (
            SERVICE_VALIDATE_PLATFORM,
            handle_validate_platform,
            PLATFORM_SCHEMA,
        ),
        (
            SERVICE_INSTALL_PLATFORM,
            handle_install_platform,
            PLATFORM_SCHEMA,
        ),
        (
            SERVICE_ROLLBACK_PLATFORM,
            handle_rollback_platform,
            PLATFORM_ROLLBACK_SCHEMA,
        ),
    )

    for service, handler, schema in response_services:
        hass.services.async_register(
            DOMAIN,
            service,
            handler,
            schema=schema,
            supports_response=SupportsResponse.ONLY,
        )

    return True


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> bool:
    manager = DeploymentManager(
        config_root=Path(hass.config.path()),
        inbox_rel=DEFAULT_INBOX,
        staging_rel=DEFAULT_STAGING,
        backups_rel=DEFAULT_BACKUPS,
        state_rel=DEFAULT_STATE,
        platform_updates_rel=DEFAULT_PLATFORM_UPDATES,
    )
    hass.data.setdefault(DOMAIN, {})["manager"] = manager

    # A platform update is considered confirmed once the new version
    # successfully loads its config entry after restart.
    await hass.async_add_executor_job(
        manager.confirm_pending_platform_update,
        VERSION,
    )
    return True


async def async_unload_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> bool:
    hass.data.get(DOMAIN, {}).pop("manager", None)
    return True
