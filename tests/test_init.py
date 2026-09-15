"""Tests for Napper config entry setup."""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.napper.const import (
    CONF_ACCOUNT_ID,
    CONF_DEVICE_ID,
    CONF_ID_TOKEN,
    CONF_POLL_INTERVAL_SECONDS,
    CONF_REFRESH_TOKEN,
    DOMAIN,
)
from custom_components.napper.models import NapperBaby, NapperLog


async def test_setup_creates_entities_for_each_baby(hass) -> None:
    """Test coordinator setup and platform forwarding."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="account-1",
        data={
            CONF_ACCOUNT_ID: "account-1",
            CONF_DEVICE_ID: "device-1",
            CONF_ID_TOKEN: "id-token",
            CONF_REFRESH_TOKEN: "refresh-token",
        },
    )
    entry.add_to_hass(hass)

    baby = NapperBaby(id="baby-1", name="Test Baby", is_owner=True)
    nap = NapperLog.from_dict(
        {
            "id": "nap-1",
            "category": "NAP",
            "isOpen": True,
            "start": "2026-09-15T13:00:00Z",
            "pauses": [],
        }
    )

    with (
        patch(
            "custom_components.napper.async_get_clientsession",
            return_value=MagicMock(),
        ),
        patch(
            "custom_components.napper.api.NapperApiClient.async_get_babies",
            new=AsyncMock(return_value=(baby,)),
        ),
        patch(
            "custom_components.napper.api.NapperApiClient.async_get_today",
            new=AsyncMock(return_value=(nap,)),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert hass.states.get("binary_sensor.test_baby_sleeping").state == "on"
    assert hass.states.get("binary_sensor.test_baby_napping").state == "on"
    assert hass.states.get("binary_sensor.test_baby_nursing").state == "off"
    assert hass.states.get("sensor.test_baby_sleep_state").state == "napping"
    assert hass.states.get("sensor.test_baby_sleep_started_at").state == (
        "2026-09-15T13:00:00+00:00"
    )

    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_only_options_changes_reload_integration(hass) -> None:
    """Test token updates do not reload, while option updates do."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="account-1",
        data={
            CONF_ACCOUNT_ID: "account-1",
            CONF_DEVICE_ID: "device-1",
            CONF_ID_TOKEN: "id-token",
            CONF_REFRESH_TOKEN: "refresh-token",
        },
    )
    entry.add_to_hass(hass)
    baby = NapperBaby(id="baby-1", name="Test Baby", is_owner=True)

    with (
        patch(
            "custom_components.napper.async_get_clientsession",
            return_value=MagicMock(),
        ),
        patch(
            "custom_components.napper.api.NapperApiClient.async_get_babies",
            new=AsyncMock(return_value=(baby,)),
        ),
        patch(
            "custom_components.napper.api.NapperApiClient.async_get_today",
            new=AsyncMock(return_value=()),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.runtime_data.coordinator.update_interval == timedelta(seconds=60)

    with patch.object(
        hass.config_entries, "async_reload", new=AsyncMock(return_value=True)
    ) as async_reload:
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, CONF_ID_TOKEN: "new-id-token"}
        )
        await hass.async_block_till_done()
        async_reload.assert_not_awaited()

        hass.config_entries.async_update_entry(
            entry, options={CONF_POLL_INTERVAL_SECONDS: 120}
        )
        await hass.async_block_till_done()
        async_reload.assert_awaited_once_with(entry.entry_id)

    assert await hass.config_entries.async_unload(entry.entry_id)
