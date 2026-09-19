from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
from typing import Any

from aiohasupervisor import SupervisorError
from aiohasupervisor.models import (
    AddonBoot,
    AddonState as SupervisorAddonState,
    AddonsOptions,
    PartialBackupOptions,
    StoreAddonUpdate,
    StoreAddRepository,
)
from homeassistant.components.hassio import AddonState
from homeassistant.components.hassio.handler import get_supervisor_client
from homeassistant.core import HomeAssistant

from .const import (
    JNS_REPOSITORY_URL,
    SFTP_APP_NAME,
    SFTP_APP_PORT,
    SFTP_APP_SLUG,
    SFTP_MIN_PASSWORD_LENGTH,
    SFTP_USERNAME,
)

_LOGGER = logging.getLogger(__name__)

_REPOSITORY_READY_TIMEOUT = 60.0
_APP_READY_TIMEOUT = 120.0
_APP_START_TIMEOUT = 60.0
_POLL_INTERVAL = 2.0
_MAX_DETAIL_LENGTH = 500


class SftpProvisioningError(RuntimeError):
    """Raised when the JNS SFTP companion app cannot be provisioned."""

    def __init__(self, stage: str, detail: str | None = None) -> None:
        # Backward-compatible one-argument construction is retained for
        # enrollment-specific call sites while v5.4.3-style failures carry a
        # precise Supervisor stage and sanitized detail.
        if detail is None:
            detail = stage
            stage = "sftp"
        self.stage = stage
        self.detail = _safe_detail(detail)
        super().__init__(f"{stage}: {self.detail}")


@dataclass(frozen=True, slots=True)
class SftpProvisionResult:
    """Safe result returned after companion app provisioning."""

    addon_slug: str
    repository_added: bool
    addon_installed: bool
    addon_created: bool
    running: bool
    version: str | None
    update_available: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "addon_slug": self.addon_slug,
            "repository_added": self.repository_added,
            "addon_installed": self.addon_installed,
            "addon_created": self.addon_created,
            "running": self.running,
            "version": self.version,
            "update_available": self.update_available,
            "host_port": SFTP_APP_PORT,
            "username": SFTP_USERNAME,
        }


@dataclass(frozen=True, slots=True)
class _AddonSnapshot:
    """Minimal Supervisor app state without strict full-model parsing."""

    available: bool
    state: AddonState
    version: str | None
    update_available: bool


def _safe_detail(value: object) -> str:
    """Return a short, single-line diagnostic safe to show in the config flow."""
    text = str(value).replace("\r", " ").replace("\n", " ").strip()
    if not text:
        return "No additional detail was returned by Home Assistant Supervisor."
    return text[:_MAX_DETAIL_LENGTH]


def _provisioning_error(stage: str, err: BaseException) -> SftpProvisioningError:
    """Convert an implementation exception into a stage-specific safe error."""
    return SftpProvisioningError(stage, f"{type(err).__name__}: {_safe_detail(err)}")


def normalize_repository_url(url: str) -> str:
    """Normalize a repository URL for equality checks."""
    normalized = url.strip().rstrip("/")
    if normalized.lower().endswith(".git"):
        normalized = normalized[:-4]
    return normalized.lower()


def validate_sftp_password(password: str) -> str:
    """Validate the transport password without logging or persisting a derivative."""
    if not isinstance(password, str) or len(password) < SFTP_MIN_PASSWORD_LENGTH:
        raise ValueError(
            f"SFTP password must contain at least {SFTP_MIN_PASSWORD_LENGTH} characters."
        )
    if any(char in password for char in ("\r", "\n", "\x00")):
        raise ValueError("SFTP password contains an unsupported control character.")
    return password


async def _async_find_repository(hass: HomeAssistant):
    client = get_supervisor_client(hass)
    wanted = normalize_repository_url(JNS_REPOSITORY_URL)
    for repository in await client.store.repositories_list():
        candidates = (
            getattr(repository, "source", ""),
            getattr(repository, "url", ""),
        )
        if any(normalize_repository_url(value) == wanted for value in candidates if value):
            return repository
    return None


async def _async_wait_for_repository(hass: HomeAssistant):
    """Wait for Supervisor to finish indexing a newly added or reloaded repository."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + _REPOSITORY_READY_TIMEOUT
    last_error: BaseException | None = None
    while loop.time() < deadline:
        try:
            repository = await _async_find_repository(hass)
            if repository is not None:
                return repository
        except SupervisorError as err:
            last_error = err
        await asyncio.sleep(_POLL_INTERVAL)

    if last_error is not None:
        raise _provisioning_error("repository_discovery", last_error)
    raise SftpProvisioningError(
        "repository_discovery",
        "Timed out waiting for Supervisor to expose the JNS app repository.",
    )


async def async_ensure_repository(hass: HomeAssistant):
    """Ensure the JNS GitHub repo is registered and freshly indexed by Supervisor."""
    client = get_supervisor_client(hass)
    try:
        repository = await _async_find_repository(hass)
    except SupervisorError as err:
        raise _provisioning_error("repository_list", err) from err

    if repository is not None:
        # v5.4.3 production fix: app metadata can change independently of the
        # HACS integration. Force a Supervisor store refresh before using it.
        try:
            await client.store.reload()
        except SupervisorError as err:
            _LOGGER.warning("Supervisor store reload for JNS repository failed: %s", err)
        return await _async_wait_for_repository(hass), False

    try:
        await client.store.add_repository(StoreAddRepository(repository=JNS_REPOSITORY_URL))
    except SupervisorError as err:
        # A duplicate/race may report an error even though the repository now exists.
        try:
            repository = await _async_find_repository(hass)
        except SupervisorError:
            repository = None
        if repository is None:
            raise _provisioning_error("repository_add", err) from err
        return repository, False

    try:
        await client.store.reload()
    except SupervisorError as err:
        _LOGGER.warning("Supervisor store reload after JNS repository add failed: %s", err)

    repository = await _async_wait_for_repository(hass)
    return repository, True


def addon_slug_for_repository(repository: Any) -> str:
    """Return the Supervisor-scoped slug for JNS Secure SFTP."""
    repository_slug = str(getattr(repository, "slug", "")).strip()
    if not repository_slug:
        raise SftpProvisioningError("repository_metadata", "Supervisor returned an invalid JNS repository slug.")
    return f"{repository_slug}_{SFTP_APP_SLUG}"


def _desired_config(
    password: str = "",
    *,
    authorized_keys: list[str] | None = None,
    password_authentication: bool = True,
) -> dict[str, Any]:
    return {
        "username": SFTP_USERNAME,
        "password": password,
        "authorized_keys": list(authorized_keys or []),
        "password_authentication": bool(password_authentication),
    }


async def _async_addon_snapshot(
    hass: HomeAssistant, addon_slug: str
) -> _AddonSnapshot:
    """Read only the Supervisor fields JNS needs.

    Home Assistant 2026.9 can return installed add-on payloads without the
    legacy hostname field. The full installed-add-on model treats that
    field as mandatory, so JNS uses list models for operational state.
    """
    client = get_supervisor_client(hass)
    store_entry = next(
        (addon for addon in await client.store.addons_list() if addon.slug == addon_slug),
        None,
    )
    if store_entry is None:
        return _AddonSnapshot(False, AddonState.NOT_INSTALLED, None, False)
    if not store_entry.installed:
        return _AddonSnapshot(
            bool(store_entry.available),
            AddonState.NOT_INSTALLED,
            store_entry.version,
            bool(store_entry.update_available),
        )

    installed = next(
        (addon for addon in await client.addons.list() if addon.slug == addon_slug),
        None,
    )
    if installed is None:
        return _AddonSnapshot(
            bool(store_entry.available),
            AddonState.NOT_RUNNING,
            store_entry.version,
            bool(store_entry.update_available),
        )

    state = (
        AddonState.RUNNING
        if installed.state is SupervisorAddonState.STARTED
        else AddonState.NOT_RUNNING
    )
    return _AddonSnapshot(
        bool(store_entry.available),
        state,
        installed.version or store_entry.version,
        bool(installed.update_available),
    )


async def _async_wait_for_app(
    hass: HomeAssistant, addon_slug: str
) -> _AddonSnapshot:
    """Wait until the repository app is queryable and available for install."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + _APP_READY_TIMEOUT
    last_error: BaseException | None = None

    while loop.time() < deadline:
        try:
            info = await _async_addon_snapshot(hass, addon_slug)
            if info.state is not AddonState.NOT_INSTALLED or info.available:
                return info
        except SupervisorError as err:
            last_error = err
        await asyncio.sleep(_POLL_INTERVAL)

    if last_error is not None:
        raise _provisioning_error("app_discovery", last_error)
    raise SftpProvisioningError(
        "app_discovery",
        "Timed out waiting for JNS Secure SFTP to become available in the Supervisor app store.",
    )


async def _async_wait_for_running(
    hass: HomeAssistant, addon_slug: str
) -> _AddonSnapshot:
    """Wait for an installed JNS SFTP app to report running."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + _APP_START_TIMEOUT
    last = await _async_addon_snapshot(hass, addon_slug)
    while loop.time() < deadline:
        if last.state is AddonState.RUNNING:
            return last
        await asyncio.sleep(_POLL_INTERVAL)
        last = await _async_addon_snapshot(hass, addon_slug)
    return last


async def async_existing_authorized_keys(hass: HomeAssistant) -> list[str]:
    """Return current SFTP authorized keys without exposing any password.

    Use the installed-app list and dedicated options/config endpoint instead of
    deserializing the full add-on info model. Supervisor may return store-like
    data without installed-only fields such as hostname while an app is not
    installed or still settling, which must not abort PC enrollment.
    """
    try:
        repository = await _async_find_repository(hass)
        if repository is None:
            return []
        addon_slug = addon_slug_for_repository(repository)
        client = get_supervisor_client(hass)
        installed = next(
            (addon for addon in await client.addons.list() if addon.slug == addon_slug),
            None,
        )
        if installed is None:
            return []
        options = await client.addons.addon_config(addon_slug)
        if not isinstance(options, dict):
            return []
        keys = options.get("authorized_keys", [])
        return [str(item).strip() for item in keys if str(item).strip()] if isinstance(keys, list) else []
    except (SupervisorError, SftpProvisioningError):
        return []


async def async_apply_management_keys(
    hass: HomeAssistant, authorized_keys: list[str]
) -> SftpProvisionResult:
    """Provision JNS SFTP in public-key-only mode for enrolled management PCs."""
    clean = sorted({str(item).strip() for item in authorized_keys if str(item).strip()})
    if not clean:
        raise SftpProvisioningError(
            "app_configure",
            "At least one enrolled management-PC SSH public key is required.",
        )

    repository, repository_added = await async_ensure_repository(hass)
    addon_slug = addon_slug_for_repository(repository)
    info = await _async_wait_for_app(hass, addon_slug)
    created = info.state is AddonState.NOT_INSTALLED
    client = get_supervisor_client(hass)

    if created:
        try:
            await client.store.install_addon(addon_slug)
        except SupervisorError as err:
            raise _provisioning_error("app_install", err) from err

    try:
        old_options = await client.addons.addon_config(addon_slug)
        if not isinstance(old_options, dict):
            old_options = {}
        await client.addons.set_addon_options(
            addon_slug,
            AddonsOptions(
                config=_desired_config(
                    str(old_options.get("password", "")),
                    authorized_keys=clean,
                    password_authentication=False,
                ),
                boot=AddonBoot.AUTO,
                auto_update=False,
                network={"22/tcp": SFTP_APP_PORT},
            ),
        )
    except SupervisorError as err:
        raise _provisioning_error("app_configure", err) from err

    try:
        info = await _async_addon_snapshot(hass, addon_slug)
        if info.state is AddonState.RUNNING:
            await client.addons.restart_addon(addon_slug)
        else:
            await client.addons.start_addon(addon_slug)
        info = await _async_wait_for_running(hass, addon_slug)
    except SupervisorError as err:
        raise _provisioning_error("app_start", err) from err

    if info.state is not AddonState.RUNNING:
        raise SftpProvisioningError(
            "app_start",
            f"Supervisor completed provisioning but reported state '{info.state.value}'.",
        )

    return SftpProvisionResult(
        addon_slug=addon_slug,
        repository_added=repository_added,
        addon_installed=True,
        addon_created=created,
        running=True,
        version=info.version,
        update_available=info.update_available,
    )


async def async_disable_management_transport(hass: HomeAssistant) -> dict[str, Any]:
    """Clear all management-PC keys and stop SFTP when no credential remains."""
    try:
        repository = await _async_find_repository(hass)
        if repository is None:
            return {"installed": False, "running": False, "authorized_key_count": 0}
        addon_slug = addon_slug_for_repository(repository)
        info = await _async_addon_snapshot(hass, addon_slug)
        if info.state is AddonState.NOT_INSTALLED:
            return {"installed": False, "running": False, "authorized_key_count": 0}

        client = get_supervisor_client(hass)
        old_options = await client.addons.addon_config(addon_slug)
        if not isinstance(old_options, dict):
            old_options = {}
        await client.addons.set_addon_options(
            addon_slug,
            AddonsOptions(
                config=_desired_config(
                    str(old_options.get("password", "")),
                    authorized_keys=[],
                    password_authentication=False,
                ),
                boot=AddonBoot.AUTO,
                auto_update=False,
                network={"22/tcp": SFTP_APP_PORT},
            ),
        )
        if info.state is AddonState.RUNNING:
            await client.addons.stop_addon(addon_slug)
        return {
            "installed": True,
            "running": False,
            "authorized_key_count": 0,
            "addon_slug": addon_slug,
        }
    except SupervisorError as err:
        raise _provisioning_error("app_disable", err) from err


async def _async_apply_options(
    hass: HomeAssistant, addon_slug: str, password: str
) -> bool:
    """Apply exact transport options and return True when a restart is needed."""
    client = get_supervisor_client(hass)
    await client.addons.addon_config(addon_slug)
    desired_config = _desired_config(password)
    desired_network = {"22/tcp": SFTP_APP_PORT}
    await client.addons.set_addon_options(
        addon_slug,
        AddonsOptions(
            config=desired_config,
            boot=AddonBoot.AUTO,
            auto_update=False,
            network=desired_network,
        ),
    )
    # Re-applying network/boot policy may require a restart even when the
    # rendered app options themselves are unchanged.
    return True


async def async_ensure_sftp_app(
    hass: HomeAssistant, password: str
) -> SftpProvisionResult:
    """Install/configure/start the JNS SFTP app using supported Supervisor APIs."""
    validate_sftp_password(password)

    try:
        repository, repository_added = await async_ensure_repository(hass)
        addon_slug = addon_slug_for_repository(repository)
    except SftpProvisioningError:
        raise
    except SupervisorError as err:
        raise _provisioning_error("repository", err) from err

    info = await _async_wait_for_app(hass, addon_slug)
    created = info.state is AddonState.NOT_INSTALLED
    client = get_supervisor_client(hass)

    if created:
        try:
            await client.store.install_addon(addon_slug)
        except SupervisorError as err:
            raise _provisioning_error("app_install", err) from err

    try:
        await _async_apply_options(hass, addon_slug, password)
    except SupervisorError as err:
        raise _provisioning_error("app_configure", err) from err

    try:
        info = await _async_addon_snapshot(hass, addon_slug)
        if info.state is AddonState.RUNNING:
            await client.addons.restart_addon(addon_slug)
        else:
            await client.addons.start_addon(addon_slug)
        info = await _async_wait_for_running(hass, addon_slug)
    except SupervisorError as err:
        raise _provisioning_error("app_start", err) from err

    if info.state is not AddonState.RUNNING:
        raise SftpProvisioningError(
            "app_start",
            f"Supervisor completed provisioning but reported state '{info.state.value}'.",
        )

    return SftpProvisionResult(
        addon_slug=addon_slug,
        repository_added=repository_added,
        addon_installed=True,
        addon_created=created,
        running=True,
        version=info.version,
        update_available=info.update_available,
    )


async def async_sftp_status(hass: HomeAssistant) -> dict[str, Any]:
    """Return SFTP companion status without credentials."""
    try:
        repository = await _async_find_repository(hass)
        if repository is None:
            return {
                "repository_present": False,
                "installed": False,
                "running": False,
                "host_port": SFTP_APP_PORT,
                "username": SFTP_USERNAME,
            }
        addon_slug = addon_slug_for_repository(repository)
        info = await _async_addon_snapshot(hass, addon_slug)
        options: dict[str, Any] = {}
        if info.state is not AddonState.NOT_INSTALLED:
            raw_options = await get_supervisor_client(hass).addons.addon_config(addon_slug)
            if isinstance(raw_options, dict):
                options = raw_options
        keys = options.get("authorized_keys", [])
        return {
            "repository_present": True,
            "repository_slug": repository.slug,
            "addon_slug": addon_slug,
            "installed": info.state is not AddonState.NOT_INSTALLED,
            "running": info.state is AddonState.RUNNING,
            "state": info.state.value,
            "version": info.version,
            "update_available": info.update_available,
            "host_port": SFTP_APP_PORT,
            "username": SFTP_USERNAME,
            "password_authentication": bool(options.get("password_authentication", True)),
            "authorized_key_count": len(keys) if isinstance(keys, list) else 0,
        }
    except (SupervisorError, SftpProvisioningError) as err:
        payload: dict[str, Any] = {
            "repository_present": False,
            "installed": False,
            "running": False,
            "host_port": SFTP_APP_PORT,
            "username": SFTP_USERNAME,
            "error": type(err).__name__,
        }
        if isinstance(err, SftpProvisioningError):
            payload["error_stage"] = err.stage
            payload["error_detail"] = err.detail
        return payload


async def async_update_sftp_app(hass: HomeAssistant, password: str) -> dict[str, Any]:
    """Explicitly update the companion app, then re-assert its safe configuration."""
    validate_sftp_password(password)
    repository, _ = await async_ensure_repository(hass)
    addon_slug = addon_slug_for_repository(repository)
    try:
        info = await _async_wait_for_app(hass, addon_slug)
        if info.state is AddonState.NOT_INSTALLED:
            return (await async_ensure_sftp_app(hass, password)).as_dict()

        client = get_supervisor_client(hass)
        if info.update_available:
            await client.store.addon_availability(addon_slug)
            await client.backups.partial_backup(
                PartialBackupOptions(
                    name=f"addon_{addon_slug}_{info.version}",
                    addons={addon_slug},
                )
            )
            await client.store.update_addon(
                addon_slug, StoreAddonUpdate(backup=False)
            )

        result = await async_ensure_sftp_app(hass, password)
        return result.as_dict()
    except SftpProvisioningError:
        raise
    except SupervisorError as err:
        raise _provisioning_error("app_update", err) from err


async def async_uninstall_sftp_app(hass: HomeAssistant, addon_slug: str) -> None:
    """Remove the companion app when it was created by this config entry."""
    try:
        info = await _async_addon_snapshot(hass, addon_slug)
        if info.state is AddonState.NOT_INSTALLED:
            return
        client = get_supervisor_client(hass)
        if info.state is AddonState.RUNNING:
            await client.addons.stop_addon(addon_slug)
        await client.addons.uninstall_addon(addon_slug)
    except SupervisorError as err:
        raise _provisioning_error("app_uninstall", err) from err

