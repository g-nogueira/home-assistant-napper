"""Tests for the Napper config flow."""

from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant import config_entries
from homeassistant.config_entries import SOURCE_REAUTH, SOURCE_USER
from homeassistant.const import CONF_EMAIL
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.napper.const import (
    CONF_ACCOUNT_ID,
    CONF_DEVICE_ID,
    CONF_ID_TOKEN,
    CONF_OTP,
    CONF_POLL_INTERVAL_SECONDS,
    CONF_REFRESH_TOKEN,
    DOMAIN,
)
from custom_components.napper.models import NapperTokens

TOKENS = NapperTokens(
    account_id="account-1",
    id_token="id-token",
    refresh_token="refresh-token",
    id_token_expires_at=2_000_000_000,
    refresh_token_expires_at=2_030_000_000,
)


async def test_user_flow_creates_entry(hass) -> None:
    """Test email and OTP setup."""
    with (
        patch(
            "custom_components.napper.async_setup_entry",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "custom_components.napper.config_flow.async_get_clientsession",
            return_value=MagicMock(),
        ),
        patch(
            "custom_components.napper.config_flow.NapperApiClient.async_send_otp",
            new=AsyncMock(),
        ) as send_otp,
        patch(
            "custom_components.napper.config_flow.NapperApiClient.async_email_login",
            new=AsyncMock(return_value=TOKENS),
        ) as email_login,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_USER},
            data={CONF_EMAIL: "Parent@Example.Test "},
        )

        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "otp"
        send_otp.assert_awaited_once_with("parent@example.test")

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_OTP: " 123456 "}
        )

        # A user flow creates a real entry. Remove it while the API client is
        # mocked so Home Assistant's test cleanup does not set it up later and
        # accidentally make a network request.
        await hass.config_entries.async_remove(result["result"].entry_id)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "parent@example.test"
    assert result["data"][CONF_ACCOUNT_ID] == "account-1"
    assert result["data"][CONF_ID_TOKEN] == "id-token"
    assert result["data"][CONF_REFRESH_TOKEN] == "refresh-token"
    assert len(result["data"][CONF_DEVICE_ID]) == 16
    email_login.assert_awaited_once_with("parent@example.test", "123456")


async def test_reauth_updates_existing_entry(hass) -> None:
    """Test OTP reauthentication without creating another entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="account-1",
        data={
            CONF_EMAIL: "parent@example.test",
            CONF_DEVICE_ID: "device-1",
            CONF_ACCOUNT_ID: "account-1",
            CONF_ID_TOKEN: "old-id-token",
            CONF_REFRESH_TOKEN: "old-refresh-token",
        },
    )
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.napper.config_flow.async_get_clientsession",
            return_value=MagicMock(),
        ),
        patch(
            "custom_components.napper.config_flow.NapperApiClient.async_send_otp",
            new=AsyncMock(),
        ),
        patch(
            "custom_components.napper.config_flow.NapperApiClient.async_email_login",
            new=AsyncMock(return_value=TOKENS),
        ),
        patch.object(
            config_entries.ConfigEntries,
            "async_reload",
            new=AsyncMock(return_value=True),
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_REAUTH, "entry_id": entry.entry_id},
            data=entry.data,
        )
        assert result["step_id"] == "reauth_confirm"

        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
        assert result["step_id"] == "reauth_otp"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_OTP: "123456"}
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_ID_TOKEN] == "id-token"
    assert entry.data[CONF_REFRESH_TOKEN] == "refresh-token"


async def test_options_flow_updates_poll_interval(hass) -> None:
    """Test configuring the polling interval."""
    entry = MockConfigEntry(domain=DOMAIN, unique_id="account-1")
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_POLL_INTERVAL_SECONDS: 120}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_POLL_INTERVAL_SECONDS: 120}


async def test_options_flow_rejects_too_short_poll_interval(hass) -> None:
    """Test polling values below the safe minimum are rejected."""
    entry = MockConfigEntry(domain=DOMAIN, unique_id="account-1")
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_POLL_INTERVAL_SECONDS: 29}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_POLL_INTERVAL_SECONDS: "invalid_poll_interval"}
