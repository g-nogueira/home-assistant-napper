"""Config flow for the Napper integration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import uuid4

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_EMAIL
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from . import _tokens_to_entry_data
from .api import (
    NapperApiClient,
    NapperApiError,
    NapperAuthenticationError,
    NapperConnectionError,
    NapperInvalidOtpError,
)
from .const import (
    CONF_DEVICE_ID,
    CONF_OTP,
    CONF_POLL_INTERVAL_SECONDS,
    DEFAULT_POLL_INTERVAL_SECONDS,
    DOMAIN,
    MAX_POLL_INTERVAL_SECONDS,
    MIN_POLL_INTERVAL_SECONDS,
)
from .models import NapperTokens


class NapperConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a Napper config flow."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> NapperOptionsFlow:
        """Return the options flow for this config entry."""
        return NapperOptionsFlow(config_entry)

    def __init__(self) -> None:
        self._email: str | None = None
        self._device_id: str | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect an email address and request a one-time password."""
        errors: dict[str, str] = {}
        if user_input is not None:
            self._email = user_input[CONF_EMAIL].strip().lower()
            self._device_id = uuid4().hex[:16]
            try:
                await self._async_send_otp()
            except NapperConnectionError:
                errors["base"] = "cannot_connect"
            except NapperApiError:
                errors["base"] = "invalid_email"
            else:
                return await self.async_step_otp()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {vol.Required(CONF_EMAIL, default=self._email or ""): str}
            ),
            errors=errors,
        )

    async def async_step_otp(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Exchange the one-time password for long-lived credentials."""
        if self._email is None or self._device_id is None:
            return self.async_abort(reason="invalid_flow")

        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                tokens = await self._async_login(user_input[CONF_OTP])
            except NapperInvalidOtpError:
                errors["base"] = "invalid_otp"
            except NapperConnectionError:
                errors["base"] = "cannot_connect"
            except NapperAuthenticationError:
                errors["base"] = "invalid_otp"
            except NapperApiError:
                errors["base"] = "unknown"
            else:
                return await self._async_finish_login(tokens)

        return self.async_show_form(
            step_id="otp",
            data_schema=vol.Schema({vol.Required(CONF_OTP): str}),
            errors=errors,
            last_step=True,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Start reauthentication for an existing config entry."""
        self._email = str(entry_data[CONF_EMAIL])
        self._device_id = str(entry_data[CONF_DEVICE_ID])
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm sending a new one-time password."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                await self._async_send_otp()
            except NapperConnectionError:
                errors["base"] = "cannot_connect"
            except NapperApiError:
                errors["base"] = "unknown"
            else:
                return await self.async_step_reauth_otp()

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({}),
            errors=errors,
            description_placeholders={"email": self._email or ""},
        )

    async def async_step_reauth_otp(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Complete reauthentication with a fresh OTP."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                tokens = await self._async_login(user_input[CONF_OTP])
            except NapperInvalidOtpError:
                errors["base"] = "invalid_otp"
            except NapperConnectionError:
                errors["base"] = "cannot_connect"
            except NapperApiError:
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(tokens.account_id)
                self._abort_if_unique_id_mismatch()
                return self.async_update_reload_and_abort(
                    self._get_reauth_entry(),
                    data_updates={
                        CONF_EMAIL: self._email,
                        CONF_DEVICE_ID: self._device_id,
                        **_tokens_to_entry_data(tokens),
                    },
                )

        return self.async_show_form(
            step_id="reauth_otp",
            data_schema=vol.Schema({vol.Required(CONF_OTP): str}),
            errors=errors,
            last_step=True,
        )

    async def _async_send_otp(self) -> None:
        if self._email is None or self._device_id is None:
            raise NapperApiError("Email and device ID are required")
        await self._client().async_send_otp(self._email)

    async def _async_login(self, otp: str) -> NapperTokens:
        if self._email is None or self._device_id is None:
            raise NapperApiError("Email and device ID are required")
        return await self._client().async_email_login(self._email, otp.strip())

    async def _async_finish_login(self, tokens: NapperTokens) -> ConfigFlowResult:
        await self.async_set_unique_id(tokens.account_id)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=self._email or "Napper",
            data={
                CONF_EMAIL: self._email,
                CONF_DEVICE_ID: self._device_id,
                **_tokens_to_entry_data(tokens),
            },
        )

    def _client(self) -> NapperApiClient:
        if self._device_id is None:
            raise NapperApiError("Device ID is not initialized")
        return NapperApiClient(
            async_get_clientsession(self.hass),
            self._device_id,
        )


class NapperOptionsFlow(OptionsFlow):
    """Handle Napper integration options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure the polling interval."""
        errors: dict[str, str] = {}
        if user_input is not None:
            poll_interval = user_input[CONF_POLL_INTERVAL_SECONDS]
            if not (
                MIN_POLL_INTERVAL_SECONDS
                <= poll_interval
                <= MAX_POLL_INTERVAL_SECONDS
            ):
                errors[CONF_POLL_INTERVAL_SECONDS] = "invalid_poll_interval"
            else:
                return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_POLL_INTERVAL_SECONDS,
                        default=self._config_entry.options.get(
                            CONF_POLL_INTERVAL_SECONDS,
                            DEFAULT_POLL_INTERVAL_SECONDS,
                        ),
                    ): vol.Coerce(int),
                }
            ),
            errors=errors,
        )
