from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .addon import SftpProvisioningError, async_ensure_sftp_app, validate_sftp_password
from .const import (
    CONF_SFTP_ADDON_SLUG,
    CONF_SFTP_CREATED_BY_INTEGRATION,
    CONF_SFTP_PASSWORD,
    DOMAIN,
    SFTP_APP_PORT,
    SFTP_USERNAME,
)


def _supervisor_available(flow: config_entries.ConfigFlow | config_entries.OptionsFlow) -> bool:
    return "hassio" in flow.hass.config.components


def _registry(flow: config_entries.ConfigFlow | config_entries.OptionsFlow):
    return flow.hass.data[DOMAIN]["management_registry"]


def _error_text(err: SftpProvisioningError | None) -> str:
    if err is None:
        return "No provisioning error has been recorded."
    return f"Stage: {err.stage} — {err.detail}"


class JNSDeploymentConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """v5.5 bootstrap contains no shared deployment password.

    After the integration is added, the administrator creates a one-time
    management-PC enrollment code from Configure. The approved PC then supplies
    its public SSH/signing keys and receives its own revocable HA identity.
    """

    VERSION = 3

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        if not _supervisor_available(self):
            return self.async_abort(reason="supervisor_required")
        if user_input is not None:
            return self.async_create_entry(
                title="JNS Deployment Platform",
                data={
                    "sftp_username": SFTP_USERNAME,
                    "sftp_port": SFTP_APP_PORT,
                    "enrollment_mode": True,
                },
            )
        return self.async_show_form(step_id="user", data_schema=vol.Schema({}))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> config_entries.OptionsFlow:
        return JNSDeploymentOptionsFlow(config_entry)


class JNSDeploymentOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._entry = config_entry
        self._last_session: dict[str, Any] | None = None
        self._last_provision_error: SftpProvisioningError | None = None

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        if not _supervisor_available(self):
            return self.async_abort(reason="supervisor_required")
        return self.async_show_menu(
            step_id="init",
            menu_options=["enroll_pc", "management_pcs", "legacy_transport"],
        )

    async def async_step_enroll_pc(self, user_input: dict[str, Any] | None = None):
        if user_input is None:
            return self.async_show_form(step_id="enroll_pc", data_schema=vol.Schema({}))
        self._last_session = await _registry(self).create_enrollment_session()
        return await self.async_step_enrollment_code()

    async def async_step_enrollment_code(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            return await self.async_step_init()
        session = self._last_session or await _registry(self).create_enrollment_session()
        return self.async_show_form(
            step_id="enrollment_code",
            data_schema=vol.Schema({}),
            description_placeholders={
                "enrollment_code": session["code"],
                "ttl_minutes": str(max(1, int(session["ttl_seconds"]) // 60)),
            },
        )

    async def async_step_management_pcs(self, user_input: dict[str, Any] | None = None):
        registry = _registry(self)
        state = await registry.list_pcs()
        active = [pc for pc in state["pcs"] if pc.get("status") == "active"]
        choices = {
            str(pc["device_id"]): f"{pc.get('device_name') or pc['device_id']} — {'commissioned' if pc.get('commissioned_at') else 'not commissioned'}"
            for pc in active
        }
        errors: dict[str, str] = {}
        if user_input is not None:
            action = str(user_input.get("action", "none"))
            try:
                if action.startswith("revoke:"):
                    await registry.revoke_pc(action.split(":", 1)[1])
                elif action == "revoke_legacy":
                    await registry.revoke_legacy()
                else:
                    return await self.async_step_init()
            except (ValueError, PermissionError):
                errors["base"] = "management_action_failed"
            else:
                return await self.async_step_management_pcs(None)

        actions = {"none": "Return without changes"}
        actions.update({f"revoke:{did}": f"Revoke {label}" for did, label in choices.items()})
        if state.get("legacy_sftp_key_count") or state.get("legacy_publisher_present"):
            actions["revoke_legacy"] = "Revoke legacy pre-v5.5 PC credentials (only after commissioning)"
        summary = "; ".join(choices.values()) if choices else "No enrolled management PCs yet"
        return self.async_show_form(
            step_id="management_pcs",
            data_schema=vol.Schema({vol.Required("action", default="none"): vol.In(actions)}),
            errors=errors,
            description_placeholders={
                "pc_summary": summary,
                "legacy_key_count": str(state.get("legacy_sftp_key_count", 0)),
                "legacy_publisher": "yes" if state.get("legacy_publisher_present") else "no",
            },
        )

    async def async_step_legacy_transport(self, user_input: dict[str, Any] | None = None):
        """Recovery-only compatibility path while migrating existing v5.4 installs."""
        errors: dict[str, str] = {}
        if user_input is not None:
            supplied = str(user_input.get(CONF_SFTP_PASSWORD, ""))
            password = supplied or str(self._entry.data.get(CONF_SFTP_PASSWORD, ""))
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
                old_created = bool(self._entry.data.get(CONF_SFTP_CREATED_BY_INTEGRATION, False))
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
                return await self.async_step_init()

        return self.async_show_form(
            step_id="legacy_transport",
            data_schema=vol.Schema({vol.Optional(CONF_SFTP_PASSWORD): selector.TextSelector({"type": "password"})}),
            errors=errors,
            description_placeholders={
                "provision_error": _error_text(self._last_provision_error),
            },
        )
