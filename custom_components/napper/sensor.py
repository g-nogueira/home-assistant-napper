"""Sensors for Napper activity state and timestamps."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .entity import NapperEntity
from .models import NapperBabyState

SLEEP_STATES = ["awake", "napping", "nap_paused", "night_sleeping", "night_waking"]


@dataclass(frozen=True, kw_only=True)
class NapperSensorEntityDescription(SensorEntityDescription):
    """Describe a Napper sensor."""

    value_fn: Callable[[NapperBabyState], Any]


SENSOR_DESCRIPTIONS = (
    NapperSensorEntityDescription(
        key="sleep_state",
        translation_key="sleep_state",
        device_class=SensorDeviceClass.ENUM,
        icon="mdi:sleep",
        value_fn=lambda state: state.sleep_state,
    ),
    NapperSensorEntityDescription(
        key="sleep_started_at",
        translation_key="sleep_started_at",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:clock-start",
        value_fn=lambda state: state.sleep_started_at,
    ),
    NapperSensorEntityDescription(
        key="last_activity_at",
        translation_key="last_activity_at",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:history",
        value_fn=lambda state: state.last_activity_at,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Napper sensors."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        NapperSensor(coordinator, baby_id, description)
        for baby_id in coordinator.data
        for description in SENSOR_DESCRIPTIONS
    )


class NapperSensor(NapperEntity, SensorEntity):
    """A sensor derived from one baby's activity logs."""

    entity_description: NapperSensorEntityDescription

    def __init__(self, coordinator, baby_id, description) -> None:
        super().__init__(coordinator, baby_id, description.key)
        self.entity_description = description
        if description.device_class == SensorDeviceClass.ENUM:
            self._attr_options = SLEEP_STATES

    @property
    def native_value(self) -> str | datetime | None:
        """Return the latest derived state."""
        return self.entity_description.value_fn(self.baby_state)
