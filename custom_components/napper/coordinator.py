"""Data coordinator for the Napper integration."""

from __future__ import annotations

import asyncio
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    NapperApiClient,
    NapperApiError,
    NapperAuthenticationError,
    NapperRateLimitError,
)
from .const import DOMAIN, UPDATE_INTERVAL
from .models import NapperBaby, NapperBabyState, derive_baby_state

_LOGGER = logging.getLogger(__name__)


class NapperDataUpdateCoordinator(DataUpdateCoordinator[dict[str, NapperBabyState]]):
    """Coordinate the shared Napper polling cycle."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: NapperApiClient,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
            always_update=False,
        )
        self.client = client
        self.babies: tuple[NapperBaby, ...] = ()

    async def _async_setup(self) -> None:
        """Load stable account metadata before the first poll."""
        try:
            self.babies = await self.client.async_get_babies()
        except NapperAuthenticationError as err:
            raise ConfigEntryAuthFailed(
                "Napper credentials are no longer valid"
            ) from err
        except NapperApiError as err:
            raise UpdateFailed(f"Unable to load Napper babies: {err}") from err

        if not self.babies:
            raise UpdateFailed("The Napper account has no babies")

    async def _async_update_data(self) -> dict[str, NapperBabyState]:
        """Fetch and derive current state for every baby."""
        now = dt_util.now()
        try:
            logs_by_baby = await asyncio.gather(
                *(self.client.async_get_today(baby.id, now) for baby in self.babies)
            )
        except NapperAuthenticationError as err:
            raise ConfigEntryAuthFailed(
                "Napper credentials are no longer valid"
            ) from err
        except NapperRateLimitError as err:
            raise UpdateFailed("Napper rate limit reached", retry_after=60) from err
        except NapperApiError as err:
            raise UpdateFailed(f"Error communicating with Napper: {err}") from err

        return {
            baby.id: derive_baby_state(baby, logs)
            for baby, logs in zip(self.babies, logs_by_baby, strict=True)
        }
