from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import voluptuous as vol
from homeassistant.components import persistent_notification
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
    DEFAULT_AUDIT,
    DEFAULT_BACKUPS,
    DEFAULT_INBOX,
    DEFAULT_PLATFORM_UPDATES,
    DEFAULT_QUARANTINE,
    DEFAULT_RECOVERY,
    DEFAULT_STAGING,
    DEFAULT_STATE,
    DEFAULT_TRUST,
    DOMAIN,
    VERSION,
    CONF_SFTP_ADDON_SLUG,
    CONF_SFTP_CREATED_BY_INTEGRATION,
    CONF_SFTP_PASSWORD,
)
from .addon import (
    SftpProvisioningError,
    async_ensure_sftp_app,
    async_sftp_status,
    async_uninstall_sftp_app,
    async_update_sftp_app,
)
from .deployment import DeploymentError, DeploymentManager
from .ha_config_check import summarize_config_check_result
from .management_pc import EnrollmentView, ManagementPCRegistry

SERVICE_STATUS = "status"
SERVICE_LIST_PUBLISHERS = "list_trusted_publishers"
SERVICE_VERIFY_AUDIT = "verify_audit_log"
SERVICE_LIST_INBOX = "list_inbox_packages"
SERVICE_PLAN = "plan_package"
SERVICE_VALIDATE = "validate_package"
SERVICE_INSTALL = "install_package"
SERVICE_QUARANTINE = "quarantine_package"
SERVICE_ROLLBACK = "rollback_transaction"
SERVICE_RECOVER = "recover_interrupted_transaction"
SERVICE_LIST_TRANSACTIONS = "list_transactions"
SERVICE_GET_TRANSACTION = "get_transaction"
SERVICE_LIST_INSTALLED = "list_installed_packages"
SERVICE_UNINSTALL = "uninstall_package"
SERVICE_VALIDATE_PLATFORM = "validate_platform_update"
SERVICE_INSTALL_PLATFORM = "install_platform_update"
SERVICE_ROLLBACK_PLATFORM = "rollback_platform_update"
SERVICE_SFTP_STATUS = "sftp_status"
SERVICE_REPAIR_SFTP = "repair_sftp"
SERVICE_UPDATE_SFTP = "update_sftp"
SERVICE_BEGIN_PC_ENROLLMENT = "begin_management_pc_enrollment"
SERVICE_LIST_MANAGEMENT_PCS = "list_management_pcs"
SERVICE_COMMISSION_MANAGEMENT_PC = "commission_management_pc"
SERVICE_REVOKE_MANAGEMENT_PC = "revoke_management_pc"
SERVICE_REVOKE_LEGACY_PC_CREDENTIALS = "revoke_legacy_pc_credentials"

PACKAGE_SCHEMA = vol.Schema({vol.Required("package"): cv.string})
INSTALL_SCHEMA = vol.Schema(
    {
        vol.Required("package"): cv.string,
        vol.Optional("dry_run", default=False): cv.boolean,
        vol.Optional("check_config", default=True): cv.boolean,
    }
)
QUARANTINE_SCHEMA = vol.Schema(
    {
        vol.Required("package"): cv.string,
        vol.Required("reason"): cv.string,
    }
)
ROLLBACK_SCHEMA = vol.Schema(
    {
        vol.Required("transaction_id"): cv.string,
        vol.Optional("force", default=False): cv.boolean,
        vol.Optional("check_config", default=True): cv.boolean,
    }
)
TRANSACTION_SCHEMA = vol.Schema({vol.Required("transaction_id"): cv.string})
UNINSTALL_SCHEMA = vol.Schema({vol.Required("package_id"): cv.string, vol.Optional("force", default=False): cv.boolean, vol.Optional("check_config", default=True): cv.boolean})
LIST_SCHEMA = vol.Schema(
    {
        vol.Optional("limit", default=50): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=100)
        )
    }
)
PLATFORM_SCHEMA = vol.Schema(
    {
        vol.Required("package"): cv.string,
        vol.Optional("dry_run", default=False): cv.boolean,
    }
)

DEVICE_SCHEMA = vol.Schema({vol.Required("device_id"): cv.string})


def _get_manager(hass: HomeAssistant) -> DeploymentManager:
    manager = hass.data.get(DOMAIN, {}).get("manager")
    if not isinstance(manager, DeploymentManager):
        raise ServiceValidationError("JNS Deployment Platform is not loaded.")
    return manager


def _get_async_lock(hass: HomeAssistant) -> asyncio.Lock:
    lock = hass.data.get(DOMAIN, {}).get("async_lock")
    if not isinstance(lock, asyncio.Lock):
        raise ServiceValidationError("JNS asynchronous operation lock is unavailable.")
    return lock


def _get_management_registry(hass: HomeAssistant) -> ManagementPCRegistry:
    registry = hass.data.get(DOMAIN, {}).get("management_registry")
    if not isinstance(registry, ManagementPCRegistry):
        raise ServiceValidationError("JNS management-PC registry is unavailable.")
    return registry


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
        raise HomeAssistantError(f"JNS filesystem operation failed: {exc}") from exc


async def _check_config(hass: HomeAssistant) -> dict[str, Any]:
    try:
        result = await conf_util.async_check_ha_config_file(hass)
        return summarize_config_check_result(result)
    except HomeAssistantError:
        raise
    except Exception as exc:
        raise HomeAssistantError(
            f"Home Assistant configuration validation failed unexpectedly: {exc}"
        ) from exc


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    domain_data = hass.data.setdefault(DOMAIN, {})
    registry = domain_data.get("management_registry")
    if not isinstance(registry, ManagementPCRegistry):
        registry = ManagementPCRegistry(hass)
        domain_data["management_registry"] = registry
        hass.http.register_view(EnrollmentView(registry))

    async def handle_status(call: ServiceCall) -> ServiceResponse:
        return await _executor_call(hass, _get_manager(hass).get_status, VERSION)

    async def handle_publishers(call: ServiceCall) -> ServiceResponse:
        return await _executor_call(hass, _get_manager(hass).list_trusted_publishers)

    async def handle_audit(call: ServiceCall) -> ServiceResponse:
        return await _executor_call(hass, _get_manager(hass).verify_audit_log)

    async def handle_list_inbox(call: ServiceCall) -> ServiceResponse:
        return await _executor_call(hass, _get_manager(hass).list_inbox_packages)

    async def handle_plan(call: ServiceCall) -> ServiceResponse:
        return await _executor_call(
            hass, _get_manager(hass).plan_package, call.data["package"]
        )

    async def handle_validate(call: ServiceCall) -> ServiceResponse:
        result = await _executor_call(
            hass, _get_manager(hass).validate_package, call.data["package"]
        )
        hass.bus.async_fire(f"{DOMAIN}_validation_result", result)
        return result

    async def handle_install(call: ServiceCall) -> ServiceResponse | None:
        manager = _get_manager(hass)
        async with _get_async_lock(hass):
            result = await _executor_call(
                hass,
                manager.install_package,
                call.data["package"],
                call.data.get("dry_run", False),
            )
            if result.get("installed") and call.data.get("check_config", True):
                try:
                    check_result = await _check_config(hass)
                except Exception:
                    await _executor_call(
                        hass, manager.rollback_transaction, result["transaction_id"], False
                    )
                    raise
                if check_result["status"] == "failed":
                    await _executor_call(
                        hass, manager.rollback_transaction, result["transaction_id"], False
                    )
                    raise ServiceValidationError(
                        "Home Assistant configuration validation failed. "
                        f"JNS rolled back transaction {result['transaction_id']}: "
                        + "; ".join(check_result["errors"])
                    )
                result["home_assistant_config_check"] = check_result
            elif result.get("installed"):
                result["home_assistant_config_check"] = {"status": "skipped"}
            hass.bus.async_fire(f"{DOMAIN}_deployment_result", result)
            return result if call.return_response else None

    async def handle_quarantine(call: ServiceCall) -> ServiceResponse | None:
        async with _get_async_lock(hass):
            result = await _executor_call(
                hass,
                _get_manager(hass).quarantine_package,
                call.data["package"],
                call.data["reason"],
            )
            return result if call.return_response else None

    async def handle_rollback(call: ServiceCall) -> ServiceResponse | None:
        manager = _get_manager(hass)
        async with _get_async_lock(hass):
            result = await _executor_call(
                hass,
                manager.rollback_transaction,
                call.data["transaction_id"],
                call.data.get("force", False),
            )
            if call.data.get("check_config", True):
                result["home_assistant_config_check"] = await _check_config(hass)
            hass.bus.async_fire(f"{DOMAIN}_rollback_result", result)
            return result if call.return_response else None

    async def handle_recover(call: ServiceCall) -> ServiceResponse | None:
        async with _get_async_lock(hass):
            result = await _executor_call(
                hass,
                _get_manager(hass).recover_interrupted_transaction,
                call.data["transaction_id"],
            )
            hass.bus.async_fire(f"{DOMAIN}_recovery_result", result)
            return result if call.return_response else None

    async def handle_list_transactions(call: ServiceCall) -> ServiceResponse:
        return await _executor_call(
            hass,
            _get_manager(hass).list_transactions,
            call.data.get("limit", 50),
        )

    async def handle_get_transaction(call: ServiceCall) -> ServiceResponse:
        return await _executor_call(
            hass,
            _get_manager(hass).get_transaction,
            call.data["transaction_id"],
        )

    async def handle_list_installed(call: ServiceCall) -> ServiceResponse:
        return await _executor_call(hass, _get_manager(hass).list_installed_packages)

    async def handle_uninstall(call: ServiceCall) -> ServiceResponse | None:
        manager = _get_manager(hass)
        async with _get_async_lock(hass):
            result = await _executor_call(
                hass, manager.uninstall_package, call.data["package_id"], call.data.get("force", False)
            )
            if call.data.get("check_config", True):
                result["home_assistant_config_check"] = await _check_config(hass)
            hass.bus.async_fire(f"{DOMAIN}_uninstall_result", result)
            return result if call.return_response else None

    async def handle_validate_platform(call: ServiceCall) -> ServiceResponse:
        return await _executor_call(
            hass,
            _get_manager(hass).validate_platform_update,
            call.data["package"],
            VERSION,
        )

    async def handle_install_platform(call: ServiceCall) -> ServiceResponse | None:
        async with _get_async_lock(hass):
            result = await _executor_call(
                hass,
                _get_manager(hass).install_platform_update,
                call.data["package"],
                VERSION,
                call.data.get("dry_run", False),
            )
            hass.bus.async_fire(f"{DOMAIN}_platform_update_result", result)
            return result if call.return_response else None

    async def handle_rollback_platform(call: ServiceCall) -> ServiceResponse | None:
        async with _get_async_lock(hass):
            result = await _executor_call(
                hass,
                _get_manager(hass).rollback_platform_update,
                call.data["transaction_id"],
            )
            hass.bus.async_fire(f"{DOMAIN}_platform_rollback_result", result)
            return result if call.return_response else None

    async def handle_sftp_status(call: ServiceCall) -> ServiceResponse:
        return await async_sftp_status(hass)

    async def _stored_sftp_password() -> str:
        entries = hass.config_entries.async_entries(DOMAIN)
        if not entries or not (password := entries[0].data.get(CONF_SFTP_PASSWORD)):
            raise ServiceValidationError(
                "JNS Secure SFTP is not configured. Open the JNS integration options first."
            )
        return password

    async def handle_repair_sftp(call: ServiceCall) -> ServiceResponse | None:
        try:
            result = await async_ensure_sftp_app(hass, await _stored_sftp_password())
        except SftpProvisioningError as exc:
            raise ServiceValidationError(str(exc)) from exc
        return result.as_dict() if call.return_response else None

    async def handle_update_sftp(call: ServiceCall) -> ServiceResponse | None:
        try:
            result = await async_update_sftp_app(
                hass, await _stored_sftp_password()
            )
        except SftpProvisioningError as exc:
            raise ServiceValidationError(str(exc)) from exc
        return result if call.return_response else None

    async def handle_begin_pc_enrollment(call: ServiceCall) -> ServiceResponse:
        registry = _get_management_registry(hass)
        try:
            await registry.require_admin(call.context.user_id)
        except PermissionError as exc:
            raise ServiceValidationError(str(exc)) from exc
        return await registry.create_enrollment_session()

    async def handle_list_management_pcs(call: ServiceCall) -> ServiceResponse:
        registry = _get_management_registry(hass)
        try:
            await registry.require_write_authorized(call.context.user_id)
        except PermissionError as exc:
            raise ServiceValidationError(str(exc)) from exc
        return await registry.list_pcs()

    async def handle_commission_management_pc(call: ServiceCall) -> ServiceResponse:
        registry = _get_management_registry(hass)
        try:
            return await registry.mark_commissioned(call.context.user_id)
        except PermissionError as exc:
            raise ServiceValidationError(str(exc)) from exc

    async def handle_revoke_management_pc(call: ServiceCall) -> ServiceResponse:
        registry = _get_management_registry(hass)
        try:
            await registry.require_admin(call.context.user_id)
            return await registry.revoke_pc(call.data["device_id"])
        except (PermissionError, ValueError) as exc:
            raise ServiceValidationError(str(exc)) from exc

    async def handle_revoke_legacy_pc_credentials(call: ServiceCall) -> ServiceResponse:
        registry = _get_management_registry(hass)
        try:
            await registry.require_admin(call.context.user_id)
            return await registry.revoke_legacy()
        except (PermissionError, ValueError) as exc:
            raise ServiceValidationError(str(exc)) from exc

    read_services = (
        (SERVICE_STATUS, handle_status, vol.Schema({})),
        (SERVICE_LIST_PUBLISHERS, handle_publishers, vol.Schema({})),
        (SERVICE_VERIFY_AUDIT, handle_audit, vol.Schema({})),
        (SERVICE_LIST_INBOX, handle_list_inbox, vol.Schema({})),
        (SERVICE_PLAN, handle_plan, PACKAGE_SCHEMA),
        (SERVICE_VALIDATE, handle_validate, PACKAGE_SCHEMA),
        (SERVICE_LIST_TRANSACTIONS, handle_list_transactions, LIST_SCHEMA),
        (SERVICE_GET_TRANSACTION, handle_get_transaction, TRANSACTION_SCHEMA),
        (SERVICE_LIST_INSTALLED, handle_list_installed, vol.Schema({})),
        (SERVICE_VALIDATE_PLATFORM, handle_validate_platform, PLATFORM_SCHEMA),
        (SERVICE_SFTP_STATUS, handle_sftp_status, vol.Schema({})),
        (SERVICE_LIST_MANAGEMENT_PCS, handle_list_management_pcs, vol.Schema({})),
        (SERVICE_BEGIN_PC_ENROLLMENT, handle_begin_pc_enrollment, vol.Schema({})),
        (SERVICE_COMMISSION_MANAGEMENT_PC, handle_commission_management_pc, vol.Schema({})),
    )
    for service, handler, schema in read_services:
        hass.services.async_register(
            DOMAIN,
            service,
            handler,
            schema=schema,
            supports_response=SupportsResponse.ONLY,
        )

    write_services = (
        (SERVICE_INSTALL, handle_install, INSTALL_SCHEMA),
        (SERVICE_QUARANTINE, handle_quarantine, QUARANTINE_SCHEMA),
        (SERVICE_ROLLBACK, handle_rollback, ROLLBACK_SCHEMA),
        (SERVICE_RECOVER, handle_recover, TRANSACTION_SCHEMA),
        (SERVICE_UNINSTALL, handle_uninstall, UNINSTALL_SCHEMA),
        (SERVICE_INSTALL_PLATFORM, handle_install_platform, PLATFORM_SCHEMA),
        (SERVICE_ROLLBACK_PLATFORM, handle_rollback_platform, TRANSACTION_SCHEMA),
        (SERVICE_REPAIR_SFTP, handle_repair_sftp, vol.Schema({})),
        (SERVICE_UPDATE_SFTP, handle_update_sftp, vol.Schema({})),
        (SERVICE_REVOKE_MANAGEMENT_PC, handle_revoke_management_pc, DEVICE_SCHEMA),
        (SERVICE_REVOKE_LEGACY_PC_CREDENTIALS, handle_revoke_legacy_pc_credentials, vol.Schema({})),
    )
    admin_only_services = {SERVICE_REVOKE_MANAGEMENT_PC, SERVICE_REVOKE_LEGACY_PC_CREDENTIALS}
    for service, handler, schema in write_services:
        async def guarded_handler(call: ServiceCall, _handler=handler, _service=service):
            registry = _get_management_registry(hass)
            if _service not in admin_only_services:
                try:
                    await registry.require_write_authorized(call.context.user_id)
                except PermissionError as exc:
                    raise ServiceValidationError(str(exc)) from exc
            return await _handler(call)
        hass.services.async_register(
            DOMAIN,
            service,
            guarded_handler,
            schema=schema,
            supports_response=SupportsResponse.OPTIONAL,
        )
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate pre-v5.4 config entries without blocking the deployment engine."""
    if entry.version < 3:
        hass.config_entries.async_update_entry(entry, version=3)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    manager = DeploymentManager(
        config_root=Path(hass.config.path()),
        inbox_rel=DEFAULT_INBOX,
        staging_rel=DEFAULT_STAGING,
        backups_rel=DEFAULT_BACKUPS,
        state_rel=DEFAULT_STATE,
        platform_updates_rel=DEFAULT_PLATFORM_UPDATES,
        trust_rel=DEFAULT_TRUST,
        audit_rel=DEFAULT_AUDIT,
        quarantine_rel=DEFAULT_QUARANTINE,
        recovery_rel=DEFAULT_RECOVERY,
    )
    hass.data.setdefault(DOMAIN, {})["manager"] = manager
    hass.data[DOMAIN]["async_lock"] = asyncio.Lock()
    await hass.async_add_executor_job(
        manager.install_recovery_tool,
        Path(__file__).with_name("recovery_tool.py"),
    )
    await hass.async_add_executor_job(
        manager.confirm_pending_platform_update,
        VERSION,
    )

    if "hassio" in hass.config.components:
        registry = _get_management_registry(hass)
        try:
            transport_state = await registry.ensure_transport_policy()
        except SftpProvisioningError:
            transport_state = {"mode": "unconfigured"}

        # Existing public keys win over the pre-v5.5 shared-password setting.
        # This preserves the old PC during migration and prevents a restart from
        # silently switching an enrolled installation back to password auth.
        if transport_state.get("mode") == "publickey":
            persistent_notification.async_dismiss(hass, f"{DOMAIN}_sftp_setup")
        else:
            password = entry.data.get(CONF_SFTP_PASSWORD)
            if password:
                try:
                    result = await async_ensure_sftp_app(hass, password)
                except SftpProvisioningError:
                    persistent_notification.async_create(
                        hass,
                        "JNS Secure SFTP legacy recovery could not be provisioned. Use JNS Deployment Platform → Configure → Enrol a new management PC, or use Legacy transport recovery only if needed.",
                        title="JNS deployment transport needs attention",
                        notification_id=f"{DOMAIN}_sftp_setup",
                    )
                else:
                    if entry.data.get(CONF_SFTP_ADDON_SLUG) != result.addon_slug:
                        hass.config_entries.async_update_entry(
                            entry,
                            data={**entry.data, CONF_SFTP_ADDON_SLUG: result.addon_slug},
                        )
            else:
                persistent_notification.async_create(
                    hass,
                    "Enrol a JNS management PC from Settings → Devices & services → JNS Deployment Platform → Configure. The first approved PC will provision key-only SFTP automatically.",
                    title="Enrol a JNS management PC",
                    notification_id=f"{DOMAIN}_sftp_setup",
                )
    return True


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove the companion SFTP app only when JNS originally installed it."""
    persistent_notification.async_dismiss(hass, f"{DOMAIN}_sftp_setup")
    if not entry.data.get(CONF_SFTP_CREATED_BY_INTEGRATION, False):
        return
    addon_slug = entry.data.get(CONF_SFTP_ADDON_SLUG)
    if not addon_slug or "hassio" not in hass.config.components:
        return
    try:
        await async_uninstall_sftp_app(hass, addon_slug)
    except SftpProvisioningError:
        # Removing the integration should not become impossible because an app
        # is already missing/unavailable. Supervisor logs retain the detail.
        return


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.get(DOMAIN, {}).pop("manager", None)
    hass.data.get(DOMAIN, {}).pop("async_lock", None)
    return True
