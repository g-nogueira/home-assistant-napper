"""The Napper Home Assistant integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import NapperApiClient
from .const import (
    CONF_ACCOUNT_ID,
    CONF_DEVICE_ID,
    CONF_ID_TOKEN,
    CONF_ID_TOKEN_EXPIRES_AT,
    CONF_REFRESH_TOKEN,
    CONF_REFRESH_TOKEN_EXPIRES_AT,
    PLATFORMS,
)
from .coordinator import NapperDataUpdateCoordinator
from .models import NapperTokens


@dataclass(slots=True)
class NapperRuntimeData:
    """Objects kept for the lifetime of a config entry."""

    client: NapperApiClient
    coordinator: NapperDataUpdateCoordinator


type NapperConfigEntry = ConfigEntry[NapperRuntimeData]


async def async_setup_entry(hass: HomeAssistant, entry: NapperConfigEntry) -> bool:
    """Set up Napper from a config entry."""

    async def async_store_tokens(tokens: NapperTokens) -> None:
        hass.config_entries.async_update_entry(
            entry,
            data={**entry.data, **_tokens_to_entry_data(tokens)},
        )

    client = NapperApiClient(
        async_get_clientsession(hass),
        entry.data[CONF_DEVICE_ID],
        tokens=_tokens_from_entry_data(entry.data),
        on_tokens_updated=async_store_tokens,
    )
    coordinator = NapperDataUpdateCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = NapperRuntimeData(client, coordinator)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: NapperConfigEntry) -> bool:
    """Unload a Napper config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


def _tokens_from_entry_data(data: dict[str, Any]) -> NapperTokens:
    return NapperTokens(
        account_id=data[CONF_ACCOUNT_ID],
        id_token=data[CONF_ID_TOKEN],
        refresh_token=data[CONF_REFRESH_TOKEN],
        id_token_expires_at=data.get(CONF_ID_TOKEN_EXPIRES_AT),
        refresh_token_expires_at=data.get(CONF_REFRESH_TOKEN_EXPIRES_AT),
    )


def _tokens_to_entry_data(tokens: NapperTokens) -> dict[str, Any]:
    return {
        CONF_ACCOUNT_ID: tokens.account_id,
        CONF_ID_TOKEN: tokens.id_token,
        CONF_REFRESH_TOKEN: tokens.refresh_token,
        CONF_ID_TOKEN_EXPIRES_AT: tokens.id_token_expires_at,
        CONF_REFRESH_TOKEN_EXPIRES_AT: tokens.refresh_token_expires_at,
    }
