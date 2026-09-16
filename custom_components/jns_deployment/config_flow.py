from __future__ import annotations

import asyncio
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .addon import (
    SftpProvisionResult,
    SftpProvisioningError,
    async_ensure_sftp_app,
    validate_sftp_password,
)
from .const import (
    CONF_SFTP_ADDON_SLUG,
    CONF_SFTP_CREATED_BY_INTEGRATION,
    CONF_SFTP_PASSWORD,
    DOMAIN,
    SFTP_APP_PORT,
    SFTP_USERNAME,
)


def _password_schema(*, required: bool) -> vol.Schema:
    key = vol.Required(CONF_SFTP_PASSWORD) if required else vol.Optional(CONF_SFTP_PASSWORD)
    return vol.Schema({key: selector.TextSelector({"type": "password"})})


def _supervisor_available(flow: config_entries.ConfigFlow | config_entries.OptionsFlow) -> bool:
    return "hassio" in flow.hass.config.components


def _error_text(err: SftpProvisioningError | None) -> str:
    if err is None:
        return "No provisioning error has been recorded."
    return f"Stage: {err.stage} — {err.detail}"


class JNSDeploymentConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 2

    def __init__(self) -> None:
        self._pending_password: str | None = None
        self._provision_task: asyncio.Task[SftpProvisionResult] | None = None
        self._provision_result: SftpProvisionResult | None = None
        self._show_provision_error = False
        self._last_provision_error: SftpProvisioningError | None = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        if not _supervisor_available(self):
            return self.async_abort(reason="supervisor_required")

        errors: dict[str, str] = {}
        if self._show_provision_error:
            errors["base"] = "cannot_provision_sftp"
            self._show_provision_error = False

        if user_input is not None:
            password = user_input[CONF_SFTP_PASSWORD]
            try:
                validate_sftp_password(password)
            except ValueError:
                errors[CONF_SFTP_PASSWORD] = "invalid_password"
            else:
                self._pending_password = password
                self._last_provision_error = None
                self._provision_task = self.hass.async_create_task(
                    async_ensure_sftp_app(self.hass, password),
                    "provision JNS Secure SFTP",
                )
                return await self.async_step_provision_sftp()

        return self.async_show_form(
            step_id="user",
            data_schema=_password_schema(required=True),
            errors=errors,
            description_placeholders={
                "provision_error": _error_text(self._last_provision_error)
            },
        )

    async def async_step_provision_sftp(self, user_input: dict[str, Any] | None = None):
        if self._provision_task is None:
            return await self.async_step_user()
        if not self._provision_task.done():
            return self.async_show_progress(
                step_id="provision_sftp",
                progress_action="provision_sftp",
                progress_task=self._provision_task,
            )
        try:
            self._provision_result = await self._provision_task
        except SftpProvisioningError as err:
            self._last_provision_error = err
            self._provision_task = None
            self._show_provision_error = True
            return self.async_show_progress_done(next_step_id="user")
        self._provision_task = None
        return self.async_show_progress_done(next_step_id="finish")

    async def async_step_finish(self, user_input: dict[str, Any] | None = None):
        if self._pending_password is None or self._provision_result is None:
            return await self.async_step_user()
        result = self._provision_result
        return self.async_create_entry(
            title="JNS Deployment Platform",
            data={
                CONF_SFTP_PASSWORD: self._pending_password,
                CONF_SFTP_ADDON_SLUG: result.addon_slug,
                CONF_SFTP_CREATED_BY_INTEGRATION: result.addon_created,
                "sftp_username": SFTP_USERNAME,
                "sftp_port": SFTP_APP_PORT,
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        return JNSDeploymentOptionsFlow(config_entry)


class JNSDeploymentOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._entry = config_entry
        self._last_provision_error: SftpProvisioningError | None = None

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        if not _supervisor_available(self):
            return self.async_abort(reason="supervisor_required")

        errors: dict[str, str] = {}
        if user_input is not None:
            supplied = user_input.get(CONF_SFTP_PASSWORD, "")
            password = supplied or self._entry.data.get(CONF_SFTP_PASSWORD, "")
            try:
                validate_sftp_password(password)
                result = await async_ensure_sftp_app(self.hass, password)
            except ValueError:
                errors[CONF_SFTP_PASSWORD] = "invalid_password"
            except SftpProvisioningError as err:
                self._last_provision_error = err
                errors["base"] = "cannot_provision_sftp"
            else:
                self._last_provision_error = None
                old_created = bool(
                    self._entry.data.get(CONF_SFTP_CREATED_BY_INTEGRATION, False)
                )
                self.hass.config_entries.async_update_entry(
                    self._entry,
                    data={
                        **self._entry.data,
                        CONF_SFTP_PASSWORD: password,
                        CONF_SFTP_ADDON_SLUG: result.addon_slug,
                        CONF_SFTP_CREATED_BY_INTEGRATION: old_created or result.addon_created,
                        "sftp_username": SFTP_USERNAME,
                        "sftp_port": SFTP_APP_PORT,
                    },
                )
                return self.async_create_entry(title="", data={})

        return self.async_show_form(
            step_id="init",
            data_schema=_password_schema(required=CONF_SFTP_PASSWORD not in self._entry.data),
            errors=errors,
            description_placeholders={
                "password_state": (
                    "A password is already stored; leave this field blank to keep it."
                    if self._entry.data.get(CONF_SFTP_PASSWORD)
                    else "Enter a new deployment-only SFTP password."
                ),
                "provision_error": _error_text(self._last_provision_error),
            },
        )
