"""Binary sensors for Napper activity state."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .entity import NapperEntity
from .models import NapperBabyState


@dataclass(frozen=True, kw_only=True)
class NapperBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Describe a Napper binary sensor."""

    value_fn: Callable[[NapperBabyState], bool]


BINARY_SENSOR_DESCRIPTIONS = (
    NapperBinarySensorEntityDescription(
        key="sleeping",
        translation_key="sleeping",
        icon="mdi:sleep",
        value_fn=lambda state: state.sleeping,
    ),
    NapperBinarySensorEntityDescription(
        key="napping",
        translation_key="napping",
        icon="mdi:sleep",
        value_fn=lambda state: state.napping,
    ),
    NapperBinarySensorEntityDescription(
        key="nap_paused",
        translation_key="nap_paused",
        icon="mdi:pause-circle-outline",
        value_fn=lambda state: state.nap_paused,
    ),
    NapperBinarySensorEntityDescription(
        key="nursing",
        translation_key="nursing",
        icon="mdi:baby-bottle-outline",
        value_fn=lambda state: state.nursing,
    ),
    NapperBinarySensorEntityDescription(
        key="night_waking",
        translation_key="night_waking",
        icon="mdi:weather-night",
        value_fn=lambda state: state.night_waking,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Napper binary sensors."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        NapperBinarySensor(coordinator, baby_id, description)
        for baby_id in coordinator.data
        for description in BINARY_SENSOR_DESCRIPTIONS
    )


class NapperBinarySensor(NapperEntity, BinarySensorEntity):
    """A binary sensor derived from one baby's activity logs."""

    entity_description: NapperBinarySensorEntityDescription

    def __init__(self, coordinator, baby_id, description) -> None:
        super().__init__(coordinator, baby_id, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool:
        """Return the derived activity flag."""
        return self.entity_description.value_fn(self.baby_state)
