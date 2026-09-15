"""Tests for Napper config entry setup."""

from unittest.mock import AsyncMock, patch

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.napper.const import (
    CONF_ACCOUNT_ID,
    CONF_DEVICE_ID,
    CONF_ID_TOKEN,
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
