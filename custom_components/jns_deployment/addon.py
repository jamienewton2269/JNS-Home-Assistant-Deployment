from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

from aiohasupervisor import SupervisorError
from aiohasupervisor.models import AddonBoot, AddonsOptions, StoreAddRepository
from homeassistant.components.hassio import AddonError, AddonManager, AddonState
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


class SftpProvisioningError(RuntimeError):
    """Raised when the JNS SFTP companion app cannot be provisioned."""


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


async def async_ensure_repository(hass: HomeAssistant):
    """Ensure the JNS GitHub repo is also registered as a Supervisor app repo."""
    repository = await _async_find_repository(hass)
    if repository is not None:
        return repository, False

    client = get_supervisor_client(hass)
    try:
        await client.store.add_repository(StoreAddRepository(repository=JNS_REPOSITORY_URL))
        await client.store.reload()
    except SupervisorError as err:
        # A duplicate/race may report an error even though the repository now exists.
        repository = await _async_find_repository(hass)
        if repository is None:
            raise SftpProvisioningError(
                "Supervisor could not add the JNS app repository."
            ) from err
        return repository, False

    repository = await _async_find_repository(hass)
    if repository is None:
        raise SftpProvisioningError(
            "Supervisor did not expose the JNS app repository after adding it."
        )
    return repository, True


def addon_slug_for_repository(repository: Any) -> str:
    """Return the Supervisor-scoped slug for JNS Secure SFTP."""
    repository_slug = str(getattr(repository, "slug", "")).strip()
    if not repository_slug:
        raise SftpProvisioningError("Supervisor returned an invalid JNS repository slug.")
    return f"{repository_slug}_{SFTP_APP_SLUG}"


def _manager(hass: HomeAssistant, addon_slug: str) -> AddonManager:
    return AddonManager(hass, _LOGGER, SFTP_APP_NAME, addon_slug)


def _desired_config(password: str) -> dict[str, Any]:
    return {
        "username": SFTP_USERNAME,
        "password": password,
        "authorized_keys": [],
        "password_authentication": True,
    }


async def _async_apply_options(
    hass: HomeAssistant, addon_slug: str, password: str
) -> bool:
    """Apply exact transport options and return True when a restart is needed."""
    client = get_supervisor_client(hass)
    installed = await client.addons.addon_info(addon_slug)
    desired_config = _desired_config(password)
    desired_network = {"22/tcp": SFTP_APP_PORT}
    changed = (
        installed.options != desired_config
        or installed.boot is not AddonBoot.AUTO
        or installed.auto_update is not False
        or installed.network != desired_network
    )
    if changed:
        await client.addons.set_addon_options(
            addon_slug,
            AddonsOptions(
                config=desired_config,
                boot=AddonBoot.AUTO,
                auto_update=False,
                network=desired_network,
            ),
        )
    return changed


async def async_ensure_sftp_app(
    hass: HomeAssistant, password: str
) -> SftpProvisionResult:
    """Install/configure/start the JNS SFTP app using supported Supervisor APIs."""
    validate_sftp_password(password)
    try:
        repository, repository_added = await async_ensure_repository(hass)
        addon_slug = addon_slug_for_repository(repository)
        manager = _manager(hass, addon_slug)
        info = await manager.async_get_addon_info()
        created = info.state is AddonState.NOT_INSTALLED
        if created:
            await manager.async_install_addon()

        options_changed = await _async_apply_options(hass, addon_slug, password)
        info = await manager.async_get_addon_info()
        if info.state is AddonState.NOT_RUNNING:
            await manager.async_start_addon()
        elif info.state is AddonState.RUNNING and options_changed:
            await manager.async_restart_addon()

        info = await manager.async_get_addon_info()
        return SftpProvisionResult(
            addon_slug=addon_slug,
            repository_added=repository_added,
            addon_installed=info.state is not AddonState.NOT_INSTALLED,
            addon_created=created,
            running=info.state is AddonState.RUNNING,
            version=info.version,
            update_available=info.update_available,
        )
    except (AddonError, SupervisorError) as err:
        raise SftpProvisioningError(
            "Supervisor could not provision JNS Secure SFTP. Check Supervisor/App logs."
        ) from err


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
        info = await _manager(hass, addon_slug).async_get_addon_info()
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
        }
    except (AddonError, SupervisorError, SftpProvisioningError) as err:
        return {
            "repository_present": False,
            "installed": False,
            "running": False,
            "host_port": SFTP_APP_PORT,
            "username": SFTP_USERNAME,
            "error": type(err).__name__,
        }


async def async_update_sftp_app(hass: HomeAssistant, password: str) -> dict[str, Any]:
    """Explicitly update the companion app, then re-assert its safe configuration."""
    validate_sftp_password(password)
    repository, _ = await async_ensure_repository(hass)
    addon_slug = addon_slug_for_repository(repository)
    manager = _manager(hass, addon_slug)
    try:
        info = await manager.async_get_addon_info()
        if info.state is AddonState.NOT_INSTALLED:
            return (await async_ensure_sftp_app(hass, password)).as_dict()
        if info.update_available:
            await manager.async_update_addon()
        result = await async_ensure_sftp_app(hass, password)
        return result.as_dict()
    except (AddonError, SupervisorError) as err:
        raise SftpProvisioningError("JNS Secure SFTP update failed.") from err


async def async_uninstall_sftp_app(hass: HomeAssistant, addon_slug: str) -> None:
    """Remove the companion app when it was created by this config entry."""
    manager = _manager(hass, addon_slug)
    try:
        info = await manager.async_get_addon_info()
        if info.state is AddonState.NOT_INSTALLED:
            return
        if info.state is AddonState.RUNNING:
            await manager.async_stop_addon()
        await manager.async_uninstall_addon()
    except AddonError as err:
        raise SftpProvisioningError("JNS Secure SFTP uninstall failed.") from err
